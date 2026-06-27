import requests
import os
import os
from dotenv import load_dotenv
import filelogger
import deepseek

def main():
    """
        Save a json response file from database endpoint
    """

    endpoint = os.getenv("ENDPOINT")
    apiKey = os.getenv("API_KEY")
    proxyPath = os.getenv("PROXY")
    header = {
        "apikey": apiKey
    }

    try:
        if proxyPath == None:
            filelogger.logger.info(f"Sending GET request to {endpoint}")
            response = requests.get(endpoint, headers=header)
            if response.status_code == 200:
                with open("data.json", "w", encoding="utf-8") as file:
                        file.write(response.text)

        else:
            filelogger.logger.info(f"Sending GET request to {endpoint}")
            response = requests.get(endpoint, headers=header, proxies=proxyPath)
            if response.status_code == 200:
                with open("data.json", "w", encoding="utf-8") as file:
                    file.write(response.text)
    
    except requests.exceptions.HTTPError as e:
        filelogger.logger.error(e)
        return None
    except Exception as e:
        filelogger.logger.error(e)
        return None

if __name__ == "__main__":
    main()
    deepseek()