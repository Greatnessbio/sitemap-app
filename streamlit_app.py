import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

def get_sitemap(base_url):
    sitemap_urls = ['/sitemap.xml', '/sitemap_index.xml', '/sitemap1.xml', '/sitemap-index.xml', '/post-sitemap.xml']
    
    for sitemap_url in sitemap_urls:
        try:
            url = urljoin(base_url, sitemap_url)
            response = requests.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            urls = [element.text for element in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
            if urls:
                st.success(f"Successfully fetched sitemap from {url}")
                return urls
        except Exception as e:
            st.warning(f"Failed to fetch sitemap from {url}: {str(e)}")
    
    st.warning("Could not find a valid sitemap. Using only the main URL.")
    return [base_url]

def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    response = requests.get(jina_url)
    if response.status_code == 200:
        return response.text
    else:
        return "Failed to fetch content"

def main():
    st.title('Web Scraper App with Sitemap and Jina Reader')

    website = st.text_input('Enter website URL (including http:// or https://):')
    
    if st.button('Fetch Sitemap and Content'):
        if website:
            urls = get_sitemap(website)
            
            # Create a DataFrame for the sitemap
            sitemap_df = pd.DataFrame({'URL': urls})
            
            st.subheader("Sitemap URLs:")
            st.dataframe(sitemap_df)
            
            # Fetch content for each URL
            content_data = []
            for url in urls:
                content = get_jina_reader_content(url)
                content_data.append({
                    'URL': url,
                    'Content Preview': content[:500] + "..." if len(content) > 500 else content
                })
            
            # Create a DataFrame for the content
            content_df = pd.DataFrame(content_data)
            
            st.subheader("Scraped Content:")
            st.dataframe(content_df)
            
            # Option to view full content for a selected URL
            selected_url = st.selectbox("Select a URL to view full content:", urls)
            if selected_url:
                full_content = get_jina_reader_content(selected_url)
                st.text_area(f"Full content for {selected_url}", full_content, height=400)
        else:
            st.warning('Please enter a website URL')

if __name__ == "__main__":
    main()
