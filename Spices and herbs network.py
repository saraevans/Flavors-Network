#!/usr/bin/env python
# coding: utf-8

# # Flavor's Network Data Collection #
# ## Using scrapy spiders to collect spices, herbs, and recipes ##

# In[13]:


#imports
import requests
from bs4 import BeautifulSoup
from scrapy import Selector
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
import scrapy
import scrapy.crawler as crawler
from multiprocessing import Process, Queue
from twisted.internet import reactor
import pandas as pd
import numpy as np
import csv


# recipes site='https://www.seriouseats.com/recipes/topics/cuisine
# spice_sites = 'https://www.thespicehouse.com/collections/letter-a', ''https://spicesinc.com/t-list-of-spices.aspx'
# 
# since scrapy spiders can't be rerun without restarting the kernel, this function found from [stack overflow](https://stackoverflow.com/questions/41495052/scrapy-reactor-not-restartable) 

# In[2]:


#for making tweaks to spider
def run_spider(spider):
    def f(q):
        try:
            runner = crawler.CrawlerRunner()
            deferred = runner.crawl(spider)
            deferred.addBoth(lambda _: reactor.stop())
            reactor.run()
            q.put(None)
        except Exception as e:
            q.put(e)

    q = Queue()
    p = Process(target=f, args=(q,))
    p.start()
    result = q.get()
    p.join()

    if result is not None:
        raise result


# In[3]:


class SpiceSpider(scrapy.Spider):
    name = 'spice_spider'
    def start_requests(self):
        url = 'https://www.thespicehouse.com/collections/letter-q'
        yield scrapy.Request(url = url, callback = self.parse_links)
    def parse_links(self, response):
        #find all the pages with spices listed on them
        links = ['https://www.thespicehouse.com' + i.extract() for i in response.css('header.section__head > div.container li > a::attr(href)')]
        for link in links:
            yield response.follow(url = link, callback = self.parse_page)
    def parse_page(self, response):
        #scrape all spices on page
        spices = response.css('h3.product__title > a::text').extract()
        #make all lowe case, clean up, and only retain the name of the spice not information after comma
        sub_lst = [i.lower().replace('\n','').strip().split(',')[0] for i in spices]
        global spice_list
        [spice_list.append(spice) for spice in sub_lst]


# In[4]:


class SpiceHerb(scrapy.Spider):
    name = 'spice_herb'
    def start_requests(self):
        url = 'https://spicesinc.com/t-list-of-spices.aspx'
        yield scrapy.Request(url = url, callback = self.parse)
    def parse(self, response):
        #get them spices + herbs
        spice_herb = response.xpath('/html/body/div[3]/div/div/div[2]/div/article/div/section/p/strong/text()')
        [spice_list.append(i.extract().lower()[:-2]) for i in spice_herb]


# In[5]:


class recipeSpider(scrapy.Spider):
    name = 'recipe_spider'
    cuisines = []
    
    def start_requests(self):
        url = 'https://www.seriouseats.com/recipes/topics/cuisine'
        yield scrapy.Request(url = url, callback = self.parse_first_pg)
        
    def parse_first_pg(self, response):
        #find the cuisine names the site uses and put them into list for cuisines
        main_cuis_path = '//*[@id="expanded-nav-Narrow by type"]/div[2]/ul/li/a/text()'
        sub_cuis_path = '//*[@id="expanded-nav-Narrow by type"]/div[2]/ul/li/ul/li/a/text()'
        
        main_cuis = response.xpath(main_cuis_path).extract()
        sub_cuis = response.xpath(sub_cuis_path).extract()
        total_cuis = main_cuis+sub_cuis
        
        global cuisines
        cuisines = total_cuis
        
        #find all recipes links on page
        recipe_links = response.xpath('/html/body/div[3]/section[1]/section/article/a/@href').extract()
        
        #find the total number of recipe pages 
        last_page_num = int(response.xpath('/html/body/div[3]/section[1]/div/div/a[3]/text()').extract_first())
        
        #input page number into standard url for the next pages
        std_url = 'https://www.seriouseats.com/recipes/topics/cuisine?page={}#recipes'
        nxt_pg_urls = [std_url.format(pg) for pg in range(2,last_page_num+1)]
        
        #send next pages to be parsed for recipe urls, and first page recipe urls are sent to be parsed for info
        for nxt in nxt_pg_urls:
            yield response.follow(url = nxt, callback = self.parse_next)
        for link in recipe_links:
            yield response.follow(url = link, callback = self.parse_recipes)

    def parse_next(self, response):
        #find recipe links on each page
        recipe_links = response.xpath('/html/body/div[3]/section[1]/section/article/a/@href').extract()
        
        for link in recipe_links:
            yield response.follow(url = link, callback = self.parse_recipes)
    
    def parse_recipes(self, response):
        #extract title, cuisine, ingreds, recipe, rating
        title = response.css('h1.recipe-title::text').extract_first()
        
        #cuisine placement unpredictable, find all info in the area then filter for cuisines found in parse_first_pg
        hidden_cuisine_path = '//div[@class = "breadcrumbs__more"]/ul/li/a/strong/text()'
        hidden_cuisine = [i.strip() for i in response.xpath(hidden_cuisine_path).extract()]

        cuisine = [c for c in cuisines if c in ' '.join(hidden_cuisine)]
        
        ingredients_path = '//*[@id="recipe-wrapper"]/div[2]/ul/li//text()'
        ingredients = ' '.join(response.xpath(ingredients_path).extract())
        
        directions_path = '//*[@id="recipe-wrapper"]/div[3]/ol//text()'
        directions = ' '.join(response.xpath(directions_path).extract()).strip()
        
        #some recipes don't have ratings return NaN if no rating
        try:
            rating_path = '//*[@id="recipe-wrapper"]/ul/li[4]/span[2]/span/text()'
            rating = float(response.xpath(rating_path).extract_first())
        except:
            rating = np.nan
        
        #add new record to recipes df
        record = pd.DataFrame({'title':title, 
                               'cuisine':cuisine, 
                               'ingredients':ingredients, 
                               'directions':directions,
                               'rating':rating
                              })
        global recipes
        recipes = pd.concat([recipes,record])


# In[6]:


#initiate empty receptors of spider info
spice_list = []
recipes = pd.DataFrame(columns = ['title','cuisine','ingredients','directions','rating'])


Process = CrawlerProcess()
Process.crawl(SpiceSpider)
Process.crawl(SpiceHerb)
Process.crawl(recipeSpider)
Process.start()        


# In[7]:


#make sure only one entry for each spice
spices = list(set(spice_list))

#filter out scraping mistakes
not_spices = ['savory','sweeteners','physical gift card','crushgrind gift bundle',
              'kitchen essentials','paprik','water','sesame seed','cilantro leaves',
              'corn','mushrooms','stock', 'bell peppers','cumin seeds','curry leaves',
              'extract', 'vanilla extract','fenugreek leaves','dried fenugreek leaves',
              'fennel pollen', 'cocoa powder']
for i in not_spices:
    try:
        spices.remove(i)
    except:
        print(i+' is not in spices')


# In[8]:


#clean df a lil
recipes.reset_index(inplace=True, drop = True)
recipes['directions'] = recipes.directions.str.replace('\n','')


# In[9]:


#find the spices in each ingredient string
def find_spice(ingredients):
    spice_herb = []
    for i in ingredients:
        spice_herb.append([s for s in spices if s in i])
    for s in range(len(spice_herb)):
        if len(spice_herb[s]) == 0:
            spice_herb[s] = np.nan
    return spice_herb


# In[10]:


recipes['spice_herb'] = find_spice(recipes.ingredients)


# In[11]:


#how many recipes by cuisine have no hits for spices
no_spice = recipes[recipes.spice_herb.isnull()]
no_spice.groupby('cuisine').count()


# ### Save Output ###

# In[14]:


recipes.to_csv('recipes.csv')
with open('spices_herbs.txt', 'w', newline='') as myfile:
    wr = csv.writer(myfile, quoting=csv.QUOTE_ALL)
    wr.writerow(spices)


# ### Work in progress ###

# In[53]:


#work in progress from here
base_url = 'https://www.bbcgoodfood.com/recipes/category/cuisines'

class BBCRecipeSpider(scrapy.Spider):
    name = 'bbc_recipe_spider'
    
    header = {
    'User-Agent': 'My User Agent 1.0', 
    'From': 'youremail@domain.com'
    }
    
    def start_requests(self):
        url = 'https://www.bbcgoodfood.com/recipes/category/cuisines'
        header = {
            'User-Agent': 'My User Agent 1.0', 
            'From': 'youremail@domain.com'
        }
        yield scrapy.Request(url = url, headers = header, callback = self.parse_links)
    
    def parse_links(self, response):
        links = ['https://www.bbcgoodfood.com' + i.extract() for i in response.xpath('//*[@id="main-content"]/article/div/div/div/ul/li/article/h3/a/@href')]
        for link in links:
            yield response.follow(url = link, headers = header, callback = self.parse_page)
            
    def parse_page(self, response):
        recipe_links =    
        
        


# In[54]:


run_spider(BBCRecipeSpider)


# In[29]:


bbc_process = CrawlerProcess()
bbc_process.crawl(BBCRecipeSpider)
bbc_process.start()

