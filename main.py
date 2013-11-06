import os
import sys
import re
import time
import logging
import urllib
import requests
import functools
import threading
import random
import base64

from datetime import datetime, timedelta, date
from xml.etree import ElementTree

import tornado.gen
import tornado.auth
import tornado.httpserver
import tornado.options
import tornado.web
import tornado.httpclient

from tornado.options import define, options
from tornado.escape import url_escape, json_decode, json_encode

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from StringIO import StringIO

import pytumblr
from twython import Twython
from instagram.client import InstagramAPI

import settings

if settings.PATH not in sys.path:
       sys.path.append(settings.PATH)

os.environ['DJANGO_SETTINGS_MODULE'] = 'shibabot.settings'

from django.conf import settings

define('port', default=settings.TORNADO_PORT, help='run on the given port', type=int)



class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', MainHandler),
        ]
        configuration = dict(
            ui_modules = {},
            login_url='/',
            cookie_secret=settings.COOKIE_SECRET,
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            xsrf_cookies=True,
            debug=settings.DEBUG,
        )
        tornado.web.Application.__init__(self, handlers, **configuration)

class BaseHandler(tornado.web.RequestHandler):

    def task(self, target, *args, **kwargs):
        target_task = functools.partial(target, *args, **kwargs)

        def callback_wrapper(callback):
            callback(target_task())
            connection.close()

        def wrapper(*args, **kwargs):
            target_callback = (kwargs.get('callback'),)
            self.thread = threading.Thread(target=callback_wrapper, args=target_callback)
            self.thread.start()

        return tornado.gen.Task(wrapper)

class MainHandler(BaseHandler):
    def get(self):
        self.finish()

class ShibaBot():

    def start(self):
        photo = self.get_photo()
        tags = self.get_tags(photo['id'])
        word_list = self.get_related_words(tags)
        if word_list:
            file_data = self.create_image(photo, word_list)
            r = self.tumblr_post(file_data, photo)
            self.twitter_post(word_list[-1], r['id'])
            tornado.ioloop.IOLoop.instance().add_timeout(timedelta(hours=3), self.start)
        else:
            tornado.ioloop.IOLoop.instance().add_timeout(timedelta(seconds=5), self.start)

    def get_photo(self):
        try:
            random_page = random.randint(1,40)
            url = "%srest/?method=flickr.photos.search&api_key=%s&text=%s&extras=owner_name&page=%s&format=rest" % (settings.FLICKR_ENDPOINT, settings.FLICKR_KEY, settings.FLICKR_SEARCH, str(random_page))
            r = requests.get(url)
            root = ElementTree.fromstring(r.text.encode('utf-8'))
            random_photo = random.randint(0, int(root[0].attrib['perpage']) - 1)
            photo = root[0][random_photo].attrib
            return photo
        except:
            tornado.ioloop.IOLoop.instance().add_timeout(timedelta(seconds=5), self.start)

    def get_ig_photo(self):
        api = InstagramAPI(access_token=settings.INSTAGRAM_ACCESS_TOKEN)
        photos, next = api.tag_recent_media(count=20, tag_name="shibainu")
        for photo in photos:
            print photo.caption.text
            print photo.tags
            print "\n"


    def get_tags(self, photo_id):
        url = "%srest/?method=flickr.tags.getListPhoto&api_key=%s&photo_id=%s&format=rest" % (settings.FLICKR_ENDPOINT, settings.FLICKR_KEY, photo_id)
        r = requests.get(url)
        root = ElementTree.fromstring(r.text.encode('utf-8'))
        tags = []
        gen = (x for x in root.iter('tag') if x.text not in settings.IGNORE_LIST)
        for x in gen:
            tags.append(x.text)
        return tags

    def get_related_words(self, tags):
        try:
            for tag in reversed(tags):
                definition_url = "%s%s/definitions?limit=1&includeRelated=false&useCanonical=false&includeTags=false&api_key=%s" % (settings.WORDNIK_ENDPOINT, tag, settings.WORDNIK_KEY)
                req = requests.get(definition_url)
                definition = json_decode(req.text)

                if definition:
                    if definition[0]['partOfSpeech'] == "noun":
                        relatedWords_url = "%s%s/relatedWords?useCanonical=true&relationshipTypes=synonym&limitPerRelationshipType=10&api_key=%s" % (settings.WORDNIK_ENDPOINT, tag, settings.WORDNIK_KEY)
                        r = requests.get(relatedWords_url)
                        decoded_json = json_decode(r.text)
                        if decoded_json:
                            word_list = decoded_json[0]['words']
                            word_list.append(tag)
                            return word_list
        except:
            tornado.ioloop.IOLoop.instance().add_timeout(timedelta(seconds=5), self.start)


    def create_image(self, photo, word_list):
        if settings.DEBUG:
            img = Image.open(photo)
            img = img.resize((img.size[0] * 2, img.size[1] * 2))
            width, height = img.size
        else:
            static_url = "http://farm%s.staticflickr.com/%s/%s_%s_c.jpg" % (photo['farm'], photo['server'], photo['id'], photo['secret'])
            r = requests.get(static_url)
            img = Image.open(StringIO(r.content))
            img = img.resize((img.size[0] * 2, img.size[1] * 2))
            width, height = img.size
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(settings.PATH + "shibabot/font/comicsans.ttf", 48)
        font.fontmode = "1"

        s_count = random.randint(4,8)

        for word in word_list:
            if s_count > 0:
                draw_width = random.randint(0, width - 100)
                draw_height = random.randint(0, height - 100)
                if s_count % 2:
                    list_item = random.randint(0, len(settings.SHIBA_PREFIX) - 1)
                    word = settings.SHIBA_PREFIX[list_item] + ' ' + word
                else:
                    list_item = random.randint(0, len(settings.SHIBA_SUFFIX) - 1)
                    word = word + ' ' + settings.SHIBA_SUFFIX[list_item]

                rcolor = random.randint(0, 255)
                bcolor = random.randint(0, 255)
                gcolor = random.randint(0, 255)
                draw.text((draw_width+1, draw_height), word, (0,0,0), font=font)
                draw.text((draw_width, draw_height+1), word, (0,0,0), font=font)
                draw.text((draw_width-1, draw_height), word, (0,0,0), font=font)
                draw.text((draw_width, draw_height-1), word, (0,0,0), font=font)
                draw.text((draw_width,draw_height), word, (rcolor,bcolor,gcolor), font=font)
                s_count -= 1
            else:
                pass

        while s_count >= 0:
            draw_width = random.randint(200, width - 200)
            draw_height = random.randint(200, height - 200)
            list_item = random.randint(0, len(settings.SHIBA_WORDS) - 1)

            rcolor = random.randint(0, 255)
            bcolor = random.randint(0, 255)
            gcolor = random.randint(0, 255)
            draw.text((draw_width+1, draw_height), settings.SHIBA_WORDS[list_item], (0,0,0), font=font)
            draw.text((draw_width, draw_height+1), settings.SHIBA_WORDS[list_item], (0,0,0), font=font)
            draw.text((draw_width-1, draw_height), settings.SHIBA_WORDS[list_item], (0,0,0), font=font)
            draw.text((draw_width, draw_height-1), settings.SHIBA_WORDS[list_item], (0,0,0), font=font)
            draw.text((draw_width,draw_height), settings.SHIBA_WORDS[list_item], (rcolor,bcolor,gcolor), font=font)
            s_count -= 1
        f = open(settings.WORKSPACE + str(int(time.time())) + ".jpg", "w+")
        img = img.resize((width/2, height/2), Image.ANTIALIAS)
        img.save(f, 'jpeg')
        name = f.name
        f.close()
        return name

    def tumblr_post(self, file_data, photo_info):
        caption = "Photo from %s - http://www.flickr.com/photos/%s/%s/" % (photo_info['ownername'], photo_info['owner'], photo_info['id'])
        payload = { 'data': file_data, 'caption': caption, 'tags': "shibainu" }
        client = pytumblr.TumblrRestClient(
            settings.TUMBLR_CLIENT_KEY,
            settings.TUMBLR_CLIENT_SECRET,
            settings.TUMBLR_OAUTH_TOKEN,
            settings.TUMBLR_OAUTH_SECRET,
        )
        r = client.create_photo(settings.TUMBLR_HOSTNAME, **payload)
        return r

    def twitter_post(self, word, post_id):
        twitter = Twython(settings.TWITTER_CLIENT_KEY, settings.TWITTER_CLIENT_SECRET,
                  settings.TWITTER_OAUTH_TOKEN, settings.TWITTER_OAUTH_SECRET)
        status = "%s Shiba http://shibabot.tumblr.com/post/%s/" % (word, post_id)
        twitter.update_status(status=status)

    def test(self):
        # photo = self.get_photo()
        self.create_image('/Users/mike/me.jpg', ['beach', 'sand', 'snow', 'what'])

if __name__ == '__main__':
    application = Application()
    bot = ShibaBot()
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(application)

    if settings.DEBUG:
        bot.start()
    else:
        tornado.ioloop.IOLoop.instance().add_timeout(timedelta(hours=3), bot.start())

    tornado.ioloop.IOLoop.instance().start()
