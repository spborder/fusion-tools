"""Testing whether there is a performance difference streaming large JSON requests
"""
import os
import json
import requests

import time




def main():

    item_id = '6495a4e03e6ae3107da10dc5'
    data_url = os.environ.get('DSA_URL')+f'annotation/item/{item_id}'

    start = time.time()
    data = requests.get(data_url).json()
    end = time.time()
    print(f'Regular method: {end-start}')

    start = time.time()
    with requests.get(data_url,stream=True) as r:
        r.raise_for_status()

        json_data = ''
        chunk_count = 0
        for chunk in r.iter_content(chunk_size=8192*2):
            json_data+=chunk.decode('utf-8')
            chunk_count +=1

        r.close()
    print(f'Chunk count: {chunk_count}')    
    data = json.loads(json_data)
    end = time.time()

    print(f'With streaming: {end-start}')






if __name__=='__main__':
    main()