import os
import requests
from datetime import datetime
import gzip
import shutil
def extract_gz_file(gz_path):
    # Create the output path by removing the .gz extension
    output_path = gz_path[:-3] + ".CIF"  # Remove .gz extension

    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        print(f"File extracted successfully to {output_path}")
        return True
    except Exception as e:
        print(f"Error extracting file: {e}")
        return False

def download_cif_file():
    # Configuration
    username = "geraghty_197@hotmail.com"  # From your secrets.json
    password = "CLS!Owner!8"
    output_dir = "CIFReader/CIF Files/"
    #url = "https://publicdatafeeds.networkrail.co.uk/ntrod/CifFileAuthenticate_?type=CIF_ALL_FULL_DAILY&day=toc-full.CIF.gz"
    url = "https://publicdatafeeds.networkrail.co.uk/ntrod/CifFileAuthenticate?type=CIF_ALL_FULL_DAILY&day=toc-full.CIF.gz"

    #url = "https://publicdatafeeds.networkrail.co.uk/ntrod/CifFileAuthenticate?type=CIF_HU_TOC_FULL_DAILY&day=toc-full"

    # Create timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #filename = f"cif_full_{timestamp}.gz"
    filename = "cif.gz"

    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    try:
        #Extract only
        file_path = os.path.join(output_dir, filename)
        extract_gz_file(file_path)
        return True



        
        # Download the file
        response = requests.get(url, auth=(username, password), stream=True)
        response.raise_for_status()
        # Save the file
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"File downloaded successfully to {file_path}")

        # Extract the downloaded file
        extract_gz_file(file_path)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file: {e}")
        return False

if __name__ == "__main__":
    download_cif_file()