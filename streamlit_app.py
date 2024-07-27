import streamlit as st
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import yaml
from urllib.parse import urljoin

# Load secrets
with open('secrets.yaml') as f:
    secrets = yaml.safe_load(f)

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

def get_sitemap(url):
    response = requests.get(url)
    root = ET.fromstring(response.content)
    urls = [element.text for element in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    return urls

def get_page_content(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    return soup

def extract_links_and_downloads(soup, base_url):
    links = []
    downloads = []

    for a in soup.find_all('a', href=True):
        href = a['href']
        full_url = urljoin(base_url, href)
        
        if any(full_url.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip']):
            downloads.append(full_url)
        else:
            links.append(full_url)

    return links, downloads

def main():
    st.title('Web Scraper App')

    if check_password():
        st.success("Logged in successfully!")

        website = st.text_input('Enter website URL (including http:// or https://):')
        
        if st.button('Fetch Sitemap, Content, Links, and Downloads'):
            if website:
                sitemap_url = website + '/sitemap.xml'
                try:
                    urls = get_sitemap(sitemap_url)
                    st.write(f"Found {len(urls)} URLs in the sitemap:")
                    for url in urls:
                        st.write(f"Processing: {url}")
                        soup = get_page_content(url)
                        
                        # Extract text content
                        content = soup.get_text()
                        st.text_area(f"Content from {url}", content, height=200)
                        
                        # Extract links and downloads
                        links, downloads = extract_links_and_downloads(soup, url)
                        
                        st.write("Links found:")
                        for link in links:
                            st.write(link)
                        
                        st.write("Downloads found:")
                        for download in downloads:
                            st.write(download)
                        
                        st.write("---")  # Separator between pages
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
            else:
                st.warning('Please enter a website URL')

if __name__ == "__main__":
    main()
