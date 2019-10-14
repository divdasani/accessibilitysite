import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import TextOperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import TextRecognitionMode
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer

import os
import sys
import time

from flask import Flask, render_template, request, redirect, url_for, Response
from jinja2 import Environment, FileSystemLoader

app = Flask(__name__)

@app.route('/')
def main():
    return render_template('landing.html')

@app.route('/serve_article', methods=['POST'])
def serve_article():
    try:
        cv_client, summarizer
    except NameError:
        summarizer = LexRankSummarizer()
        cv_client = get_cv_client()
    
    url = request.form['URL']
    icon,title,text,images,captions=build_page(url,cv_client,summarizer)
  
    return render_template('index.html',icon=icon,title=title,text=text,images=images,captions=captions)

def get_soup(url):
    res = requests.get(url)
    html_page = res.content
    soup = BeautifulSoup(html_page, 'html.parser')
    return soup

def get_logo(soup, url):
    slash = url[8:].find('/')
    if slash > -1:
        head = url[0:url[8:].find('/')+8]
    else:
        head = url

    ext = soup.find("link", rel="Shortcut Icon") or soup.find("link", rel="shortcut icon")
    if not ext:
         return ''
    else:
        ext = ext['href']
        if ext.find('http') == -1 and ext.find('.com') == -1:
            icon = head+ext
        else:
            icon = ext
        if urlparse(icon).netloc:
            return icon
        else:
            return ''
        
def is_cnn(url):
    return url.find('cnn.com') > -1

def get_body(soup, is_cnn):
    body_tags = ['a','div','p','h1','h2','h3','h4']
    body_ignore = ['Read More']
    
    text = soup.find_all(text=True)

    title = ''
    body = ''
    isbody = False
    
    if is_cnn:
        for t in text:
            tag = t.parent.name
            if tag == 'title':
                title = t
            elif tag == 'cite':
                isbody = True
            elif tag == 'body':
                break
            if isbody and tag in body_tags:
                if t not in body_ignore and t.find('http') == -1:
                    if prev == 'div':
                        body+='\n\n'
                    body += '{}'.format(t)
            prev = tag
    if not is_cnn or not body:
        for t in text:
            tag = t.parent.name
            if tag == 'title':
                title = t
            if tag in body_tags:
                t = t.replace('\n','')
                if len(t)>3 and t.find('http') == -1:
                    body += '{}'.format(t) + ' '
                    if len(t) > 25:
                        body += '\n\n'
    return title, body

def get_image(soup, is_cnn):
    images = soup.findAll('img')
    exists = []
    image_urls = []
    for image in images:
        image_url = image['src']

        if urlparse(image_url).netloc:
            if (image_url.find('.png') != -1 or 
               image_url.find('.jpg') != -1 or 
               image_url.find('.gif') != -1 or 
               image_url.find('.svg') != -1):
                if image_url[0:2] == '//':
                    image_url = image_url[2:]
                if image_url[0:4] != 'http':
                    image_url = 'http://' + image_url
                if is_cnn:
                    key = re.findall(r'/[0-9]*-',image_url)
                    if key and key[0][1:-1] not in exists:
                        exists.append(key[0][1:-1])
                        image_urls.append(image_url)
                else:
                    image_urls.append(image_url)

    image_urls = list(set(image_urls))
    mid = len(image_urls)//2
    return image_urls[max(0,mid-3):min(len(image_urls),mid+3)]

def generate_captions(images,cv_client):
    captions = []
    for image in images:
        try:
            description_results = cv_client.describe_image(image)
            if description_results.captions:
                captions.append(description_results.captions[0].text)
            else:
                captions.append('No caption available')
        except:
            captions.append('No caption available')
    return captions

def simplify_text(text, summarizer):
    sentences = len(text)//150
    
    parser = PlaintextParser.from_string(text,Tokenizer("english"))
    summary = summarizer(parser.document, sentences)
    return ' '.join([str(x) for x in summary])

def build_page(url,cv_client,summarizer):
    soup = get_soup(url)
    iscnn = is_cnn(url)
    
    title,unsimp_text = get_body(soup,iscnn)
    text = simplify_text(unsimp_text,summarizer)
    
    icon = get_logo(soup,url)
    images = get_image(soup,iscnn)
    captions = generate_captions(images,cv_client)

    return icon,title,text,images,captions

def get_cv_client():
    endpoint = 'https://westcentralus.api.cognitive.microsoft.com'
    subscription_key = 'd0fa9162e03a4c7b9cf531e88956b3e3'
    cv_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))
    return cv_client