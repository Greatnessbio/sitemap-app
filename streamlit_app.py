import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import time

# Initialize session state
if 'sitemap_urls' not in st.session_state:
    st.session_state.sitemap_urls = []
if 'content_data' not in st.session_state:
    st.session_state.content_data = []

# User agent to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True

def get_sitemap_urls(url):
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        urls = []
        for sitemap in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
            sitemap_url = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
            urls.extend(get_sitemap_urls(sitemap_url))
        for url in root.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
            loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc').text
            urls.append(loc)
        return urls
    except Exception as e:
        st.warning(f"Failed to fetch sitemap from {url}: {str(e)}")
        return []

def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    response = requests.get(jina_url)
    if response.status_code == 200:
        return response.text
    else:
        return f"Failed to fetch content: {response.status_code}"

def main():
    st.title('Web Scraper App with Sitemap and Jina Reader')

    if check_password():
        st.success("Logged in successfully!")

        website = st.text_input('Enter website URL (including http:// or https://):')
        
        if st.button('Fetch Sitemap and Content'):
            if website:
                st.session_state.sitemap_urls = get_sitemap_urls(urljoin(website, '/sitemap.xml'))
                
                if st.session_state.sitemap_urls:
                    st.subheader("Sitemap URLs:")
                    sitemap_df = pd.DataFrame({'URL': st.session_state.sitemap_urls})
                    st.dataframe(sitemap_df)
                    
                    st.subheader("Fetching Content:")
                    progress_bar = st.progress(0)
                    st.session_state.content_data = []
                    
                    for i, url in enumerate(st.session_state.sitemap_urls):
                        content = get_jina_reader_content(url)
                        st.session_state.content_data.append({
                            'URL': url,
                            'Content Preview': content[:500] + "..." if len(content) > 500 else content
                        })
                        progress_bar.progress((i + 1) / len(st.session_state.sitemap_urls))
                        time.sleep(1)  # Rate limiting
                    
                    st.subheader("Scraped Content:")
                    content_df = pd.DataFrame(st.session_state.content_data)
                    st.dataframe(content_df)
                else:
                    st.warning("No URLs found in the sitemap.")
            else:
                st.warning('Please enter a website URL')
        
        # Display tables if data exists in session state
        if st.session_state.sitemap_urls:
            st.subheader("Sitemap URLs:")
            sitemap_df = pd.DataFrame({'URL': st.session_state.sitemap_urls})
            st.dataframe(sitemap_df)
        
        if st.session_state.content_data:
            st.subheader("Scraped Content:")
            content_df = pd.DataFrame(st.session_state.content_data)
            st.dataframe(content_df)
        
        # Option to view full content for a selected URL
        if st.session_state.sitemap_urls:
            selected_url = st.selectbox("Select a URL to view full content:", st.session_state.sitemap_urls)
            if selected_url:
                full_content = get_jina_reader_content(selected_url)
                st.text_area(f"Full Jina Reader content for {selected_url}", full_content, height=400)

if __name__ == "__main__":
    main()
