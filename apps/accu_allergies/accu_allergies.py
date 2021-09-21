############################################################
#
# This class aims to get the Allergies information from Accuweather
#
# written to be run from AppDaemon for a HASS or HASSIO install
#
# Written: 30/04/2020
# Updated: 26/06/2020
# added postcode in addition to ID for some locations
############################################################
# original repository: https://github.com/simonhq/accu_allergies
# I (DavyRoswinkel)only translated some stuff for personal use.
# ! Please keep this text in tact!
############################################################
# 
# In the apps.yaml file you will need the following
# updated for your database path, stop ids and name of your flag
#
# accu_allergies:
#   module: accu_allergies
#   class: Get_Accu_Allergies
#   ACC_FILE: "./allergies"
#   ACC_FLAG: "input_boolean.get_allergies_data"
#   DEB_FLAG: "input_boolean.reset_allergies_sensor"
#   URL_ID: "21921"
#   URL_CITY: "canberra"
#   URL_COUNTRY: "au"
#   URL_LANG: "en"
#   URL_POSTCODE: ""
#
# https://www.accuweather.com/en/au/canberra/21921/allergies-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/cold-flu-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/asthma-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/arthritis-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/migraine-weather/21921
# https://www.accuweather.com/en/au/canberra/21921/sinus-weather/21921
#
############################################################

# import the function libraries for beautiful soup
from bs4 import BeautifulSoup
import json
import datetime
import appdaemon.plugins.hass.hassapi as hass
import requests
import shelve

class Get_Accu_Allergies(hass.Hass):

    ACC_FLAG = ""
    DEB_FLAG = ""
    URL_LANG = ""
    URL_COUNTRY = ""
    URL_CITY = ""
    URL_ID = ""
    URL_POSTCODE = ""
    
    payload = {}
    headers = {
        'User-Agent': 'Mozilla/5.0'
    }
        
    #"https://www.accuweather.com/URL_LANG/URL_COUNTRY/URL_CITY/URL_ID/cold-flu-weather/URL_ID"
    #url building
    url_base = "https://www.accuweather.com"
    
    # simple - asthma, arthritis, migraine, sinus
    url_txt_sets = [["/asthma-weather/","asthma"], ["/arthritis-weather/","arthritis"], ["/migraine-weather/","migraine"], [ "/sinus-weather/","sinus"], ["/air-quality-index/", "air"]]
    
    # extended - cold, flu, ragweed pollen, grass pollen, tree pollen, mold, dust
    #["/allergies-weather/","allergies"], ["/cold-flu-weather/","coldflu"]
    url_txt_xtd = [["/allergies-weather/", "?name=ragweed-pollen" , "ragweed"], ["/allergies-weather/", "?name=grass-pollen" , "grass"], ["/allergies-weather/", "?name=tree-pollen" , "tree"], ["/allergies-weather/", "?name=mold" , "mold"], ["/allergies-weather/", "?name=dust-dander" , "dust"], ["/cold-flu-weather/", "?name=common-cold" , "cold"], ["/cold-flu-weather/", "?name=flu" , "flu"]]

    def cleanString(self, s):
        retstr = ""
        for chars in s:
                retstr += self.removeNonAscii(chars)
        return retstr

    def removeNonAscii(self, s): 
        return ''.join(i for i in s if ord(i)<126 and ord(i)>31)    

    # run to setup the system
    def initialize(self):
        #get the info for the system
        self.ACC_FILE = self.args["ACC_FILE"]
        self.ACC_FLAG = self.args["ACC_FLAG"]
        self.DEB_FLAG = self.args["DEB_FLAG"]
        self.URL_LANG = self.args["URL_LANG"]
        self.URL_COUNTRY = self.args["URL_COUNTRY"]
        self.URL_CITY = self.args["URL_CITY"]
        self.URL_ID = self.args["URL_ID"]
        #see if they have included a postcode value, if not, just use the ID value
        try:
            self.URL_POSTCODE = self.args["URL_POSTCODE"]
        except:
            self.URL_POSTCODE = self.URL_ID
        #check that the postcode is blank, and if so set it to the ID value
        if self.URL_POSTCODE == "":
            self.URL_POSTCODE = self.URL_ID

        #create the original sensors
        self.load_sensors()

        #set the listener for the update flag for getting the data
        self.listen_state(self.get_all_data, self.ACC_FLAG, new="on")
        #set the listener for update flag for updating the sensor from the files
        self.listen_state(self.set_acc_sensors, self.DEB_FLAG, new="on")

        # set to run each morning at 5.07am
        runtime = datetime.time(5,7,0)
        self.run_daily(self.daily_load_sensors, runtime)
        

    #get the information from each of the pages and write them into text files for reuse
    def get_all_data(self, entity, attribute, old, new, kwargs):
        #call the data builder
        self.get_html_data()
        #turn off the flag
        self.turn_off(self.ACC_FLAG)
    
    #request the website information
    def get_html_data(self):
        #build the url for the correct country and area
        start_url = self.url_base + "/" + self.URL_LANG + "/" + self.URL_COUNTRY + "/" + self.URL_CITY + "/" + self.URL_POSTCODE
        
        #for each of the basic pages (asthma, arthritis, migraine and sinus)
        for sets in self.url_txt_sets:
            #build the url for this allergy type
            data_url = start_url + sets[0] + self.URL_ID
            #call the function to get the information and put it in the text file
            self.get_data(data_url, sets[1])

        #for each of the multi-tier pages (allergies and cold/flu)
        for sets in self.url_txt_xtd:
            #build the url for this allergy type
            data_url = start_url + sets[0] + self.URL_ID + sets[1]
            #call the function to get the information and put it in the text file
            self.get_data(data_url, sets[2])
        
    #request the website information and write it to a file
    def get_data(self, url, txt):
        # request the rendered html
        self.log("request " + url)
        data_from_website = self.get_html(url) 
        # write the html into the local shelve file
        with shelve.open(self.ACC_FILE) as allergies_db:
            allergies_db[txt] = data_from_website
        #write out the get sensor
        self.set_get_sensor()
        #update the sensor
        self.create_get_sensor()

    def set_get_sensor(self):
        #create a sensor to keep track last time this was run
        tim = datetime.datetime.now()
        date_time = tim.strftime("%d/%m/%Y, %H:%M:%S")
        #add date time to the save file
        with shelve.open(self.ACC_FILE) as allergies_db:
            allergies_db["updated"] = date_time

    def create_get_sensor(self):
        #get last update date time from the save file 
        with shelve.open(self.ACC_FILE) as allergies_db:
            date_time = allergies_db["updated"]
        #create the sensor
        self.set_state("sensor.acc_data_laatst_geupdate", state=date_time, replace=True, attributes={"icon": "mdi:timeline-clock-outline", "friendly_name": "ACC Allergie Data laatst geupdate"})

    #get the html from the website
    def get_html(self, url):
        #create request for getting information from the accuweather website
        response = requests.request("GET", url, headers=self.headers, data = self.payload)
        #scrape and return the rendered html
        return response.text.encode('utf8')

    # call the processes to create the sensors
    def set_acc_sensors(self, entity, attribute, old, new, kwargs):
        #load all the sensors
        self.load_sensors()
        #turn off the flag
        self.turn_off(self.DEB_FLAG)

    # this loads the first time run and on a restart of appdaemon
    def load_sensors(self):    
        #if no current data files
        collect_flag = 0
        with shelve.open(self.ACC_FILE) as allergies_db:
            #self.log(allergies_db[self.url_txt_sets[0][1]])
            if "updated" not in allergies_db:
                collect_flag = 1
                
        if collect_flag == 1:
            self.get_html_data()
            self.log("get")

        #create the sensors
        #pollens etc
        self.get_allergies_rag_info(self.url_txt_xtd[0][2])
        self.get_allergies_grass_info(self.url_txt_xtd[1][2])
        self.get_allergies_tree_info(self.url_txt_xtd[2][2])
        self.get_allergies_mold_info(self.url_txt_xtd[3][2])
        self.get_allergies_dust_info(self.url_txt_xtd[4][2])
        #cold and flu
        self.get_coldflu_cold_info(self.url_txt_xtd[5][2])        
        self.get_coldflu_flu_info(self.url_txt_xtd[6][2])
        #air quality
        self.get_allergies_air_info(self.url_txt_sets[4][1])
        #asthma
        self.get_asthma_info(self.url_txt_sets[0][1])
        #arthritis
        self.get_arthritis_info(self.url_txt_sets[1][1])
        #migraine
        self.get_migraine_info(self.url_txt_sets[2][1])
        #sinus
        self.get_sinus_info(self.url_txt_sets[3][1])
        #update the last updated sensor
        self.create_get_sensor()

    # this runs each morning
    def daily_load_sensors(self, kwargs):    
        #get data
        self.get_html_data()

        #load sensors
        self.load_sensors()


    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_air_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "aq-number")
        mytext = soup.find_all("p", "category-text")
        mystate = soup.find_all("p", "statement")
        

        #create the hassio sensors for today and tomorrow for ragweed        
        if(len(myvals) > 1):
            self.set_state("sensor.acc_lucht_kwaliteit_vandaag", state=myvals[0].text, replace=True, attributes={"icon": "mdi:air-purifier", "friendly_name": "Lucht Kwaliteit Vandaag", "luchtkwaliteitsindex_vandaag": myvals[0].text + " - " + mytext[0].text , "luchtkwaliteitsindex_vandaag_info": mystate[0].text })
            self.set_state("sensor.acc_lucht_kwaliteit_morgen", state=myvals[2].text, replace=True, attributes={"icon": "mdi:air-purifier", "friendly_name": "Lucht Kwaliteit Morgen", "luchtkwaliteitsindex_morgen": myvals[2].text + " - " + mytext[2].text , "luchtkwaliteitsindex_morgen_info": mystate[2].text })
        else:
            self.set_state("sensor.acc_lucht_kwaliteit_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:air-purifier", "friendly_name": "Lucht Kwaliteit Vandaag", "luchtkwaliteitsindex_vandaag": 'Onbekend' , "luchtkwaliteitsindex_vandaag_info": 'Onbekend' })
            self.set_state("sensor.acc_lucht_kwaliteit_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:air-purifier", "friendly_name": "Lucht Kwaliteit Morgen", "luchtkwaliteitsindex_morgen": 'Onbekend' , "luchtkwaliteitsindex_morgen_info": 'Onbekend' })

        
    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_rag_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for ragweed        
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_ambrosia_pollen_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:clover", "friendly_name": "Ambrosia Pollen Vandaag", "ambrosia_gehalte_vandaag": myvals[0].text , "ambrosia_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_ambrosia_pollen_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:clover", "friendly_name": "Ambrosia Pollen Morgen", "ambrosia_gehalte_morgen": myvals[1].text , "ambrosia_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_ambrosia_pollen_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:clover", "friendly_name": "Ambrosia Pollen Vandaag", "ambrosia_gehalte_vandaag": 'Onbekend' , "ambrosia_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_ambrosia_pollen_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:clover", "friendly_name": "Ambrosia Pollen Morgen", "ambrosia_gehalte_morgen": 'Onbekend' , "ambrosia_info_morgen": 'Onbekend' })


    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_grass_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for grasspollen        
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_gras_pollen_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:barley", "friendly_name": "Gras Pollen Vandaag", "graspollen_gehalte_vandaag": myvals[0].text , "gras_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_gras_pollen_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:barley", "friendly_name": "Gras Pollen Morgen", "graspollen_gehalte_morgen": myvals[1].text , "gras_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_gras_pollen_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:barley", "friendly_name": "Gras Pollen Vandaag", "graspollen_gehalte_vandaag": 'Onbekend' , "gras_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_gras_pollen_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:barley", "friendly_name": "Gras Pollen Morgen", "graspollen_gehalte_morgen": 'Onbekend' , "gras_info_morgen": 'Onbekend' })

        
    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_tree_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for tree pollen    
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_boom_pollen_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:tree-outline", "friendly_name": "Boom Pollen Vandaag", "boompollen_gehalte_vandaag": myvals[0].text , "boompollen_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_boom_pollen_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:tree-outline", "friendly_name": "Boom Pollen Morgen", "boompollen_gehalte_morgen": myvals[1].text , "boompollen_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_boom_pollen_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:tree-outline", "friendly_name": "Boom Pollen Vandaag", "boompollen_gehalte_vandaag": 'Onbekend' , "boompollen_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_boom_pollen_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:tree-outline", "friendly_name": "Boom Pollen Morgen", "boompollen_gehalte_morgen": 'Onbekend' , "boompollen_info_morgen": 'Onbekend' })


    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_mold_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for mold        
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_schimmels_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:bacteria-outline", "friendly_name": "Schimmels Vandaag", "schimmel_gehalte_vandaag": myvals[0].text , "schimmel_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_schimmels_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:bacteria-outline", "friendly_name": "Schimmels Morgen", "schimmel_gehalte_morgen": myvals[1].text , "schimmel_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_schimmels_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:bacteria-outline", "friendly_name": "Schimmels Vandaag", "schimmel_gehalte_vandaag": 'Onbekend' , "schimmel_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_schimmels_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:bacteria-outline", "friendly_name": "Schimmels Morgen", "schimmel_gehalte_morgen": 'Onbekend' , "schimmel_info_morgen": 'Onbekend' })
    

    #get the info for pollens - ragweed, grass, tree, mold, dust and air quality
    def get_allergies_dust_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")
        
        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for dust       
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_huisstofmijt_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:cloud-search-outline", "friendly_name": "Huisstofmijt Vandaag", "huisstofmijt_gehalte_vandaag": myvals[0].text , "huisstofmijt_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_huisstofmijt_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:cloud-search-outline", "friendly_name": "Huisstofmijt Morgen", "huisstofmijt_gehalte_morgen": myvals[1].text , "huisstofmijt_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_huisstofmijt_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:cloud-search-outline", "friendly_name": "Huisstofmijt Vandaag", "huisstofmijt_gehalte_vandaag": 'Onbekend' , "huisstofmijt_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_huisstofmijt_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:cloud-search-outline", "friendly_name": "Huisstofmijt Morgen", "huisstofmijt_gehalte_morgen": 'Onbekend' , "huisstofmijt_info_morgen": 'Onbekend' })
    
    #get the info for cold and flu
    def get_coldflu_cold_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for commoncold        
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_verkoudheid_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:snowflake-alert", "friendly_name": "Verkoudheid Vandaag", "verkoudheids_waarde_vandaag": myvals[0].text , "verkoudheids_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_verkoudheid_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:snowflake-alert", "friendly_name": "Verkoudheid Morgen", "verkoudheids_waarde_morgen": myvals[1].text , "verkoudheids_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_verkoudheid_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:snowflake-alert", "friendly_name": "Verkoudheid Vandaag", "verkoudheids_waarde_vandaag": 'Onbekend' , "verkoudheids_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_verkoudheid_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:snowflake-alert", "friendly_name": "Verkoudheid Morgen", "verkoudheids_waarde_morgen": 'Onbekend' , "verkoudheids_info_morgen": 'Onbekend' })
    

    def get_coldflu_flu_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")

        #create the hassio sensors for today and tomorrow for cold        
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_griep_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:bacteria", "friendly_name": "Griep Vandaag", "griep_waarde_vandaag": myvals[0].text , "griep_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_griep_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:bacteria", "friendly_name": "Griep Morgen", "griep_waarde_morgen": myvals[1].text , "griep_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_griep_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:bacteria", "friendly_name": "Griep Vandaag", "griep_waarde_vandaag": 'Onbekend' , "griep_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_griep_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:bacteria", "friendly_name": "Griep Morgen", "griep_waarde_morgen": 'Onbekend' , "griep_info_morgen": 'Onbekend' })
        
        
    #get the info for asthma
    def get_asthma_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")
        
        #create the hassio sensors for today and tomorrow for asthma
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_astma_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:lungs", "friendly_name": "Astma Vandaag", "astma_waarde_vandaag": myvals[0].text , "astma_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_astma_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:lungs", "friendly_name": "Astma Morgen", "astma_waarde_morgen": myvals[1].text , "astma_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_astma_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:lungs", "friendly_name": "Astma Vandaag", "astma_waarde_vandaag": 'Onbekend' , "astma_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_astma_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:lungs", "friendly_name": "Astma Morgen", "astma_waarde_morgen": 'Onbekend' , "astma_info_morgen": 'Onbekend' })
        

    #get the info for arthritis
    def get_arthritis_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")
        
        #create the hassio sensors for today and tomorrow for arthritis
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_artritis_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:bone", "friendly_name": "Artritis Vandaag", "artritis_waarde_vandaag": myvals[0].text , "artritis_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_artritis_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:bone", "friendly_name": "Artritis Morgen", "artritis_waarde_morgen": myvals[1].text , "artritis_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_artritis_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:bone", "friendly_name": "Artritis Vandaag", "artritis_waarde_vandaag": 'Onbekend' , "artritis_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_artritis_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:bone", "friendly_name": "Artritis Morgen", "artritis_waarde_morgen": 'Onbekend' , "artritis_info_morgen": 'Onbekend' })

    #get the info for migraine
    def get_migraine_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")
        
        #create the hassio sensors for today and tomorrow for migraine
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_migraine_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:head-flash", "friendly_name": "Migraine Vandaag", "migraine_waarde_vandaag": myvals[0].text , "migraine_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_migraine_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:head-flash", "friendly_name": "Migraine Morgen", "migraine_waarde_morgen": myvals[1].text , "migraine_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_migraine_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:head-flash", "friendly_name": "Migraine Vandaag", "migraine_waarde_vandaag": 'Onbekend' , "migraine_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_migraine_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:head-flash", "friendly_name": "Migraine Morgen", "migraine_waarde_morgen": 'Onbekend' , "migraine_info_morgen": 'Onbekend' })
        
    
    #get the info for sinus
    def get_sinus_info(self, txt):

        #open the file and read the allergies information
        with shelve.open(self.ACC_FILE) as allergies_db:
            html_info = allergies_db[txt]
        #parse the file for the hmtl
        soup = BeautifulSoup(html_info, "html.parser")

        myvals = soup.find_all("div", "gauge")
        myconds = soup.find_all("div", "cond")
        
        #create the hassio sensors for today and tomorrow for sinus
        if(len(myvals) > 1):
            myvalseta = self.cleanString(myvals[0].text.split('>'))
            myvalsetb = self.cleanString(myvals[1].text.split('>'))
            self.set_state("sensor.acc_sinushoofdpijn_vandaag", state=myvalseta, replace=True, attributes={"icon": "mdi:head-remove-outline", "friendly_name": "Sinushoofdpijn Vandaag", "sinushoofdpijn_waarde_vandaag": myvals[0].text , "sinushoofdpijn_info_vandaag": myconds[0].text })
            self.set_state("sensor.acc_sinushoofdpijn_morgen", state=myvalsetb, replace=True, attributes={"icon": "mdi:head-remove-outline", "friendly_name": "Sinushoofdpijn Morgen", "sinushoofdpijn_waarde_morgen": myvals[1].text , "sinushoofdpijn_info_morgen": myconds[1].text })
        else:
            self.set_state("sensor.acc_sinushoofdpijn_vandaag", state='Onbekend', replace=True, attributes={"icon": "mdi:head-remove-outline", "friendly_name": "Sinushoofdpijn Vandaag", "sinushoofdpijn_waarde_vandaag": 'Onbekend' , "sinushoofdpijn_info_vandaag": 'Onbekend' })
            self.set_state("sensor.acc_sinushoofdpijn_morgen", state='Onbekend', replace=True, attributes={"icon": "mdi:head-remove-outline", "friendly_name": "Sinushoofdpijn Morgen", "sinushoofdpijn_waarde_morgen": 'Onbekend' , "sinushoofdpijn_info_morgen": 'Onbekend' })

        
        
        