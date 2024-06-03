import io

import requests


def http_download(url):
    resp = requests.get(url)
    if resp.status_code == 200:
        return io.BytesIO(resp.content)


def http_download_to_file(url, local_filepath, chunk_size=8192):
    with requests.get(url, stream=True) as resp:
        if resp.status_code == 200:
            with open(local_filepath, 'wb') as out:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    out.write(chunk)
    return local_filepath
