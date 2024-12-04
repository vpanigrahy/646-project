import math 
import json
import pandas as pd
from rank_bm25 import BM25Okapi
import numpy as np
import requests
from llm_functions import *


def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    r = 3958.8
    distance = r * c
    return distance

def get_documents_within_25miles(df, latitude, longitude):
    locations_within_25km = df[df.apply(lambda row: calculate_distance(latitude, longitude, row['latitude'], row['longitude']), axis=1) < 25]
    return locations_within_25km

def distance_from_reference(location, zipcode):
    latitude, longitude = get_lat_lon(zipcode)
    return calculate_distance(latitude, longitude,
                              location["latitude"], location["longitude"])

def get_lat_lon(zipcode, country="US"):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'postalcode': zipcode,
        'country': country,
        'format': 'json'
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data:
            # Taking the first result as the most relevant one
            latitude = data[0]['lat']
            longitude = data[0]['lon']
            return float(latitude), float(longitude)
        else:
            return None, None
    else:
        return None, None

def rag(llm,meta_list, query):
    keys_to_keep = ['name','description','avg_rating','num_of_reviews','MISC']
    modified_list_of_dicts = [{k: v for k, v in d.items() if k in keys_to_keep} for d in meta_list[:5]]

    result = json.dumps(modified_list_of_dicts)
    prompt_template = """You are a restaurent recommender system that help users to find restaurents that match their preferences. Based on search query, suggest three restaurents, with a description, rating or MISC etc and the reason why the user will like it (reason should loosely be based on query).
    Your response should be concise with one restaurent on one line. Use the following information for restaurants. 
    "{context}"
    Search Query: {query}
    Your Response: """
    # PROMPT = PromptTemplate(
    # template=prompt_template, input_variables=["context", "query"])
    llm_chain = LLMChain(llm=llm, prompt=PromptTemplate.from_template(prompt_template))
    summary = llm_chain.run({"context": result, "query": query})
    # print(summary)
    return summary

def ensemble(llm,retriever, query, zipcode):
    docs = retriever.invoke(query)
    meta_dict = {}

    for doc in docs:
        gmap_id = doc.metadata["gmap_id"]
        if gmap_id not in meta_dict:
            meta_dict[gmap_id] = doc.metadata

    meta_list = list(meta_dict.values())
    # summary = rag(llm,meta_list)
    search_info = {}
    # search_info['summary'] = summary
    search_info['items'] = meta_list
    search_info['query'] = query
    return search_info

def retrieval_info(data, bm25, query, zipcode):
    
    query_tokens = query.split(" ")
    # Get document scores
    doc_scores = bm25.get_scores(query_tokens)
    data['doc_scores'] = doc_scores
    latitude, longitude = get_lat_lon(zipcode)
    
    docs = get_documents_within_25miles(data,latitude,longitude)
    
    sorted_docs = docs.sort_values(by=['doc_scores', 'avg_rating'], ascending=[False, False])
    print(sorted_docs)
    top_10_docs = sorted_docs.head(10)
    top_10_docs.fillna(' ', inplace=True)
    top_10_docs_list = top_10_docs.to_dict(orient='records')
    search_info ={}
    search_info['items'] = top_10_docs_list
    return search_info

def recommender_info(llm, data,recommender_data, gmap_id):
    row = recommender_data.loc[gmap_id].to_list()
    search_data = data.loc[data['gmap_id'] == gmap_id].to_dict(orient= 'records')
    doc = data.loc[data['gmap_id'] == gmap_id, 'doc_information'].iloc[0]
    recom_data = []

    for id in row:
        filtered_row = data.loc[data['gmap_id'] == id]
        filtered_row.fillna(' ',inplace=True)
        filtered_row_dict = filtered_row.to_dict(orient='records')
        recom_data.append(filtered_row_dict[0])

    prompt_template = """Write a concise summary of the following:
    "{text}"
    CONCISE SUMMARY: """
    llm_chain = LLMChain(llm=llm, prompt=PromptTemplate.from_template(prompt_template))
    summary = llm_chain.run({"text": doc[:20000]})
    
    recom_info ={}
    recom_info['restaurantInfo'] = search_data[0]
    recom_info['recommendations'] = recom_data
    recom_info['summary'] = summary

    return recom_info




    
