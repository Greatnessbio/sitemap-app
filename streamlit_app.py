import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# User agent to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
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

def get_sitemap(base_url):
    sitemap_urls = [
        '/sitemap.xml',
        '/sitemap_index.xml',
        '/sitemap1.xml',
        '/sitemap-index.xml',
        '/post-sitemap.xml'
    ]
    
    for sitemap_url in sitemap_urls:
        try:
            url = urljoin(base_url, sitemap_url)
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            if 'xml' in content_type:
                root = ET.fromstring(response.content)
                urls = [element.text for element in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
                if urls:
                    st.success(f"Successfully fetched sitemap from {url}")
                    return urls
        except requests.RequestException as e:
            st.warning(f"Failed to fetch sitemap from {url}: {str(e)}")
        except ET.ParseError as e:
            st.warning(f"Failed to parse XML from {url}: {str(e)}")
    
    st.warning("Could not find a valid sitemap. Falling back to scraping the main page.")
    return [base_url]

def get_page_content(url):
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except requests.RequestException as e:
        st.error(f"Failed to fetch the page content: {str(e)}")
        return None

def extract_links_and_downloads(soup, base_url):
    links = []
    downloads = []

    if soup is None:
        return links, downloads

    for a in soup.find_all('a', href=True):
        href = a['href']
        full_url = urljoin(base_url, href)
        
        if any(full_url.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip']):
            downloads.append(full_url)
        else:
            links.append(full_url)

    return links, downloads

def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    response = requests.get(jina_url)
    if response.status_code == 200:
        return response.text
    else:
        return "Failed to fetch content"

def main():
    st.title('Web Scraper App with Sitemap and Jina Reader')

    if check_password():
        st.success("Logged in successfully!")

        website = st.text_input('Enter website URL (including http:// or https://):')
        
        if st.button('Fetch Sitemap, Content, Links, and Downloads'):
            if website:
                urls = get_sitemap(website)
                
                st.write(f"Processing {len(urls)} URLs:")
                content_data = []
                for url in urls:
                    st.write(f"Processing: {url}")
                    soup = get_page_content(url)
                    
                    if soup:
                        # Extract text content
                        content = soup.get_text()
                        
                        # Extract links and downloads
                        links, downloads = extract_links_and_downloads(soup, url)
                        
                        # Get Jina Reader content
                        jina_content = get_jina_reader_content(url)
                        
                        content_data.append({
                            'URL': url,
                            'Content Preview': content[:500] + "..." if len(content) > 500 else content,
                            'Jina Content Preview': jina_content[:500] + "..." if len(jina_content) > 500 else jina_content,
                            'Links': ', '.join(links[:5]) + "..." if len(links) > 5 else ', '.join(links),
                            'Downloads': ', '.join(downloads)
                        })
                
                # Create a DataFrame for the content
                content_df = pd.DataFrame(content_data)
                
                st.subheader("Scraped Content:")
                st.dataframe(content_df)
                
                # Option to view full content for a selected URL
                selected_url = st.selectbox("Select a URL to view full content:", urls)
                if selected_url:
                    full_content = get_jina_reader_content(selected_url)
                    st.text_area(f"Full Jina Reader content for {selected_url}", full_content, height=400)
            else:
                st.warning('Please enter a website URL')

if __name__ == "__main__":
    main()
