"""
We will build a content extractor that will return a json with all the text, headings and paragraphs from a given url
result = {
    "html": "<html>Full website HTML</html>",
    "article_text": "Full body text with all headings and text",
    "article_headings": ["1", "2"],  # Array with all headings found in the text
    "article_paragraphs": [],  # Array with all paragraphs from the text
    "urls": [],  # Array with all urls in the text
    "article_content": [{"heading": "", "paragraphs": ""}, {"heading": "", "paragraphs": ""}]  # Array with all headings and paragraphs below
}
"""
# import modules
from selenium import webdriver
from selenium.webdriver import FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
import os
from bs4 import BeautifulSoup as Bs
import cfscrape
import time
from string import punctuation
import markdownify
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.request
import json
import urllib

class ChromeSession:
    """
    Class to manage a Chrome session
    """        

    def __init__(self, headless=True, options=None):
        opts = FirefoxOptions()
        opts.add_argument("--headless")
        if os.name == "nt":
            self.driver = webdriver.Firefox(options=options, service_log_path=os.path.devnull, service=FirefoxService(GeckoDriverManager().install()))
        else:
            self.driver = webdriver.Firefox(options=opts)

    def __enter__(self):
        return self.driver

    def __exit__(self, exc_type, exc_value, traceback):
        self.driver.quit()
        

def cfscrape_session():
    """
    Returns a request session with cloudflare bypassing
    """
    session = cfscrape.create_scraper()
    return session


def check_ponctuation(text, number_of_punctuation_marks=2):
    ''' Check if we have ponctuation marks in a text '''
    count = 0
    for char in text:
        if char in punctuation:
            count += 1
    if count >= number_of_punctuation_marks:
        return True
    else:
        return False


def get_youtube_transcript(url):
    '''Get youtube transcript from url'''
    # set up video id
    id = url.split('v=')[1]
    if '&' in id:
        id = id.split('&')[0]
    # get transcript from youtube
    transcript = YouTubeTranscriptApi.get_transcript(
        id, languages=['pt', 'en', 'es'])
    # print(transcript)
    transcript = ' '.join([t['text'] for t in transcript])
    return transcript


def get_youtube_information(url):

    #change to yours VideoID or change url inparams
    VideoID = url.split('v=')[1]
    if '&' in VideoID:
        VideoID = VideoID.split('&')[0]

    params = {"format": "json", "url": "https://www.youtube.com/watch?v=%s" % VideoID}
    url = "https://www.youtube.com/oembed"
    query_string = urllib.parse.urlencode(params)
    url = url + "?" + query_string

    with urllib.request.urlopen(url) as response:
        response_text = response.read()
        data = json.loads(response_text.decode())

    return data


def extract_html_from_url(url, session):
    """
    Extracts html from given url using either a Chrome session or a request session
    """
    # Check if url is valid
    if not url.startswith("http"):
        url = "http://" + url

    if 'youtube.com' in url:
        content = get_youtube_transcript(url)
        information = get_youtube_information(url)
        title = f'<h1>{information["title"]}</h1>'
        thumbnail = f'<img src="{information["thumbnail_url"]}" alt="{information["title"]}">'
        source = f'<a href="{url}">Fonte</a>'
        conteudo  = f'<p>{content}</p>'
        iframe = information['html']
        html = f'{source}{title}{thumbnail}{conteudo}{iframe}'
        return html

    # Check if session is chrome or request
    if isinstance(session, webdriver.firefox.webdriver.WebDriver):
        with session as browser_session:
            browser_session.get(url)
            # Waiting page load
            i = 0
            while i < 5:
                time.sleep(1)
                if browser_session.execute_script("return document.readyState") == "complete":
                    # scroll page a little to simulate a human user
                    browser_session.execute_script("window.scrollBy(0, 100)")
                    time.sleep(1)
                    html = browser_session.page_source
                    i = 5
                i += 1
    else:
        response = session.get(url)
        if response.status_code == 200:
            html = response.text
        else:
            html = None
    return html


def html_to_json(html):
    """
    Parse HTML to create JSON with all the article information
    """
    # start json
    result = {
        "html": html,
        "article_text": "",
        "article_headings": [],
        "article_paragraphs": [],
        "urls": [],
        "article_content": [],
        "article_html_content": "",
        "article_url": ""
        }

    # Parse HTML
    soup = Bs(html, "html.parser")

    # Get canonical url
    canonical_url = soup.find("link", {"rel": "canonical"})
    if canonical_url:
        result["article_url"] = canonical_url["href"]

    # ADVANCE FILTERING
    # We are going to iterate through all the tags inside body and get all H1, H2, H3, H4, P, OL, UL
    # For titles we will check if we have at least 1 space
    # For paragraphs we will check if we have at least 4 spaces and at least 2 punctuation marks (.,;:!?)
    # For lists we will check if we have at least 2 li and it is not a link
    # We will also check if the tag has at least 1 space
    result['advanced_content'] = []
    for tag in soup.find_all(True):
        if tag.name[0] == 'h' and tag.name[1].isdigit():
            if tag.text and " " in tag.text.strip():
                result['advanced_content'] += '<' + tag.name + '>' + tag.text + '</' + tag.name + '>'
        elif tag.name == 'p':
            if tag.text and " " in tag.text.strip() and check_ponctuation(tag.text.strip()):
                result['advanced_content'] += '<' + tag.name + '>' + tag.text + '</' + tag.name + '>'
        elif tag.name == 'ol' or tag.name == 'ul':
            if tag.text and " " in tag.text.strip() and check_ponctuation(tag.text.strip(), 1) and len(tag.find_all('li')) >= 2:
                result['advanced_content'] += '<' + tag.name + '>' + tag.text + '</' + tag.name + '>'
        elif tag.name == 'li':
            if tag.text and " " in tag.text.strip() and check_ponctuation(tag.text.strip(), 1):
                result['advanced_content'] += '<' + tag.name + '>' + tag.text + '</' + tag.name + '>'
    
    # div with most paragraphs will be te soup of the advanced content
    div_with_most_paragraphs = Bs(''.join(result['advanced_content']), "html.parser")    
    
    # Setting urls
    # Find all urls inside the div with most paragraphs
    for a in div_with_most_paragraphs.find_all('a'):
        if a.has_attr('href'):
            result["urls"].append(a['href'])

    # Setting article_html_content
    result["article_html_content"] = ""
    h1 = soup.find_all('h1')[-1]
    result['article_html_content'] += "<h1>" + h1.text + "</h1>\n"
    # iterate through all tags inside div if nested
    for tag in div_with_most_paragraphs.find_all(True):
        if tag.name == 'h2':
            result["article_html_content"] += "<h2>" + tag.text + "</h2>\n"
        elif tag.name == 'h3':
            result["article_html_content"] += "<h3>" + tag.text + "</h3>\n"
        elif tag.name == 'h4':
            result["article_html_content"] += "<h4>" + tag.text + "</h4>\n"
        elif tag.name == 'p':
            # We check if paragraph has at least one space (" ")
            # At least any punctuation anywhere in the paragraph text
            # To avoid empty paragraphs that make no sense
            if tag.text and " " in tag.text.strip() and any(p in tag.text for p in punctuation):
                result["article_html_content"] += "<p>" + tag.text.strip() + "</p>\n"
        elif tag.name == 'ol' or tag.name == 'ul':
            # We check if there is more than 1 li in the ol/ul
            # If there is, we will iterate through all li
            list = ""
            list += '<' + tag.name + '>\n'
            for li in tag.find_all('li'):
                if li.text and " " in li.text.strip():
                    list += "<li>" + li.text.strip() + "</li>\n"
            list += '</' + tag.name + '>\n'
            if len(list.split("</li>")) > 2:
                result["article_html_content"] += list

    # Now we soup the article_html_content to get the next information
    soup = Bs(result['article_html_content'], "html.parser")

    # Find all headings inside the div with most paragraphs
    # We will go up to H4
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    for heading in headings:
        result["article_headings"].append(heading.text)

    # Setting article_paragraphs
    # Find all paragraphs inside the div with most paragraphs
    paragraphs = soup.find_all('p')
    for paragraph in paragraphs:
        # Remove extra space and line breaks
        paragraph_text = paragraph.text.strip()
        paragraph_text = paragraph_text.replace("\n", " ")
        paragraph_text = paragraph_text.replace("\r", " ")
        # Remove double spaces
        while "  " in paragraph_text:
            paragraph_text = paragraph_text.replace("  ", "")
        result["article_paragraphs"].append(paragraph_text)
    
    # Setting article_content
    # Find all headings and paragraphs below the div with most paragraphs
    # We will go up to H4
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    for heading in headings:
        # Check if heading has text
        if heading.text:
            # Create a dictionary with heading and paragraphs
            # Check if heading is h1, h2... to add #, ##...
            if heading.name == 'h1':
                heading_dict = {"heading": '# ' + heading.text, "paragraphs": []}
            elif heading.name == 'h2':
                heading_dict = {"heading": '## ' + heading.text, "paragraphs": []}
            elif heading.name == 'h3':
                heading_dict = {"heading": '### ' + heading.text, "paragraphs": []}
            elif heading.name == 'h4':
                heading_dict = {"heading": '#### ' + heading.text, "paragraphs": []}
            # Find all paragraphs below the heading before the next heading
            paragraphs = heading.find_next_siblings()
            for paragraph in paragraphs:
                # Stop if finds next header
                if paragraph.name and paragraph.name.startswith('h'):
                    break
                # check if is ol
                if paragraph.name == 'ol' or paragraph.name == 'ul':
                    # Find all li inside the ol
                    for li in paragraph.find_all('li'):
                        # Check if li has text
                        if li.text:
                            # Check if li has ponctuation
                            if li.text.strip()[-1] in ['.', '?', '!',';']:
                                # Add text to heading
                                heading_dict["paragraphs"].append("- " + li.text)
                            else:
                                # Add text to heading
                                heading_dict["paragraphs"].append("- " + li.text + ".")
                else:
                    # Remove extra space and line breaks
                    paragraph_text = paragraph.text.strip()
                    paragraph_text = paragraph_text.replace("\n", " ")
                    paragraph_text = paragraph_text.replace("\r", " ")
                    # Remove double spaces
                    while "  " in paragraph_text:
                        paragraph_text = paragraph_text.replace("  ", "")
                    # Add text to heading if it has enough text
                    if len(str(paragraph_text)) > 5:
                        heading_dict["paragraphs"].append(paragraph_text)
            # Add heading and paragraphs to the result
            result["article_content"].append(heading_dict)

    # Setting article_text
    # Find all headings and paragraphs to create article text
    # We will go up to H4
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
    for heading in headings:
        # Check if heading has text
        if heading.text:
            # Add heading to article text
            result["article_text"] += heading.text + "\n\n"
        # Find all paragraphs below the heading
        paragraphs = heading.find_next_siblings()
        for paragraph in paragraphs:
            # Stop if finds next header
            if paragraph.name and paragraph.name.startswith('h'):
                break
            # check if is ol
            if paragraph.name == 'ol' or paragraph.name == 'ul':
                # Find all li inside the ol
                for li in paragraph.find_all('li'):
                    # Add text to article text
                    result["article_text"] += li.text + "\n"
            else:
                # Remove extra space and line breaks
                paragraph_text = paragraph.text.strip()
                paragraph_text = paragraph_text.replace("\n", " ")
                paragraph_text = paragraph_text.replace("\r", " ")
                # Remove double spaces
                while "  " in paragraph_text:
                    paragraph_text = paragraph_text.replace("  ", "")
                # Add paragraph to article text
                result["article_text"] += paragraph_text + "\n\n"

    # Remove extra line breaks
    while '\n\n\n' in result["article_text"]:
        result["article_text"] = result["article_text"].replace('\n\n\n', '\n\n')

    # Convert html to markdown
    result["article_markdown_content"] = markdownify.markdownify(result["article_html_content"], heading_style="ATX").replace('\n\n\n', '\n\n').replace('\n\n\n', '\n\n')

    return result


if __name__ == '__main__':
    get_youtube_information("https://www.youtube.com/watch?v=9bZkp7q19f0")

