# -*- coding: utf-8 -*-
import vim     # actually vim is imported in commentreader.vim
import urllib
import urllib2
import urlparse
import time
import json
import oauth2  # actually oauth2 is imported in commentreader.vim
import logging

# Initialization
# global variables
CR_Langdict = {
            'python':  { 'prefix':  '#', 'filler':   '#', 'suffix':   '#', 'defs':   r'^def' },
            'perl':    { 'prefix':  '#', 'filler':   '#', 'suffix':   '#', 'defs':   r'^sub' },
            'vim':     { 'prefix':  '"', 'filler':   '"', 'suffix':   '"', 'defs':   r'^function' },
            'c':       { 'prefix':  '/*', 'filler':  '*', 'suffix':   '*/', 'defs':  r''},
            'cpp':     { 'prefix':  '//', 'filler':  '//', 'suffix':  '//', 'defs':  r''},
           }

CR_Instance = {}


# Interface

def CRopenbook(bufnum, path):
    CR_Instance.setdefault(bufnum, CommentReader())
    CR_Instance[bufnum].openBook(path)

def CRopenweibo(bufnum, auth_code):
    CR_Instance.setdefault(bufnum, CommentReader())
    CR_Instance[bufnum].openWeibo(auth_code)

def CRopendouban(bufnum):
    CR_Instance.setdefault(bufnum, CommentReader())
    pass

def CRopentwitter(bufnum, PIN):
    CR_Instance.setdefault(bufnum, CommentReader())
    CR_Instance[bufnum].openTwitter(PIN)

def CRhide(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].hide()
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRclose(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].hide()
        del CR_Instance[bufnum]
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRforward(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].forward()
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRbackward(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].backward()
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRnext(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].next()
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRprevious(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].previous()
    else:
        vim.command("echoe 'No contents have been opened!'")

def CRsavesession(bufnum):
    if bufnum in CR_Instance:
        CR_Instance[bufnum].saveSession()
    else:
        vim.command("echoe 'No contents have been opened!'")

# Main

class CommentReader():
    def __init__(self):
        self.option  = {
                'line_len': int(vim.eval('g:creader_lines_per_block')),
                'line_num': int(vim.eval('g:creader_chars_per_line')),
                'session_file': vim.eval('g:creader_session_file'),
                'debug_mode': int(vim.eval('g:creader_debug_mode')),
                'debug_file': vim.eval('g:creader_debug_file'),
                }
        self.head    = None # the pointer to current content
        self.content = {}
        self.session = self.loadSession()
        self.view    = View(self.option)
        self.base    = 0
        self.offset  = 0

        # logging setting
        if self.option['debug_mode']:
            logging.basicConfig(filename=self.option['debug_file'], level=logging.DEBUG, format='%(asctime)s %(message)s')

    # session

    def saveSession(self):
        for name in self.content:
            self.session[name] = self.content[name].saveSession()
        try:
            fp = open(self.option['session_file'], 'w+')
            json.dump(self.session, fp)
        except:
            # TODO: do something
            pass

    def loadSession(self):
        try:
            fp = open(self.option['session_file'], 'r')
            return json.load(fp)
        except:
            return {}

    # opens

    def openBook(self, path):
        self.content['Book'] = Book(path, self.session.get('Book', {}), self.option)
        self.head = self.content['Book']
        self.view.refreshAnchor()
        self.show()

    def openWeibo(self, auth_code):
        # Content
        if 'Weibo' not in self.content:
            self.content['Weibo'] = Weibo(self.session.get('Weibo', {}), self.option)
        self.head = self.content['Weibo']

        if auth_code:
            self.head.reqAccessToken(auth_code)

        # View
        if self.head.ready():
            self.view.refreshAnchor()
            self.show()
        else:
            self.head.reqAuthPage()

    def openTwitter(self, PIN):
        # Content
        if 'Twitter' not in self.content:
            self.content['Twitter'] = Twitter(self.session.get('Twitter', {}), self.option)
        self.head = self.content['Twitter']

        if PIN:
            self.head.reqAccessToken(PIN)

        # View
        if self.head.ready():
            self.view.refreshAnchor()
            self.show()
        else:
            self.head.reqAuthPage()

    def refresh(self):
        self.head.refresh()
        self.base   = 0
        self.offset = 0
        self.show()

    # closes

    def close(self):
        pass

    # views

    def show(self):
        # clear first
        self.view.clear()

        # get content and render 
        # TODO: need to check the EOF
        raw_content_list = self.head.read(self.base, self.view.getAnchorNum())
        content_list = self.view.commentize_list(raw_content_list)
        self.view.render(content_list)

        # point to first block
        self.first()

    def hide(self):
        # save and restore cursor position
        (line_bak, col_bak) = (vim.eval("line('.')"), vim.eval("col('.')"))
        self.view.clear()
        vim.command("call cursor('{0}', '{1}')".format(line_bak, col_bak))

    # cursor moves

    def forward(self, seek=None):
        # TODO: return if self.base == MAX

        self.base += self.view.getAnchorNum()
        self.show()
        if seek is None:
            self.first()
        else:
            self.seek(seek)

    def backward(self, seek=None):
        if self.base == 0:
            return

        self.base -= self.view.getAnchorNum()
        if self.base < 0:
            self.base = 0
        self.show()
        if seek is None:
            self.first()
        else:
            self.seek(seek)

    # index is the current node's index in all node's array
    # index = self.base + self.offset
    def seek(self, index):
        self.offset = (index - self.base) % self.view.getAnchorNum()
        self.view.pointTo(self.offset)

    def first(self):
        self.seek(self.base)

    def last(self):
        self.seek(self.base + self.view.getAnchorNum - 1)

    def next(self):
        offset = self.offset + 1
        if offset >= self.view.getAnchorNum():
            self.forward(self.base + offset)
        else:
            self.seek(self.base + offset)

    def previous(self):
        offset = self.offset - 1
        if offset < 0:
            self.backward(self.base + offset)
        else:
            self.seek(self.base + offset)


class Anchor():
    def __init__(self, rel_posi, pre_anchor):
        self.rel_posi   = rel_posi
        self.abs_posi   = -1
        self.size       = 0
        self.pre_anchor = pre_anchor

    def evalAbsPosition(self):
        if self.pre_anchor is None:
            self.abs_posi = self.rel_posi
            return self.abs_posi
        else:
            self.abs_posi = self.pre_anchor.evalAbsPosition() + self.pre_anchor.size + self.rel_posi
            return self.abs_posi

    # Warning: if you need EXACT position, call evalAbsPosition instead of this
    def getAbsPosition(self):
        if self.abs_posi != -1:
            return self.abs_posi
        else:
            return self.evalAbsPosition()

    def bind(self, str):
        self.abs_posi = self.evalAbsPosition()
        self.size = str.count("\\n")

    def unbind(self):
        self.abs_posi = -1
        self.size = 0


class View():
    def __init__(self, option):
        # user defined options
        self.lineLen = option['line_len']
        self.lineNum = option['line_num']

        # define commenter
        filetype = vim.eval("&filetype")
        if filetype in CR_Langdict:
            self.prefix = CR_Langdict[filetype]['prefix']
            self.filler = CR_Langdict[filetype]['filler']
            self.suffix = CR_Langdict[filetype]['suffix']
        else:
            vim.command("echom 'Sorry, this language is not supported.'")
            return

        # define declaration reserved word
        self.defs = CR_Langdict[filetype]['defs']

        # define anchors
        self.anchors = []

        self.refreshAnchor()
        if self.getAnchorNum() == 0:
            vim.command("echom 'Sorry, there is no place for comment.'")
            return

    # anchors

    def getAnchorNum(self):
        return len(self.anchors)

    def refreshAnchor(self):
        # clear comment first
        self.clear()

        # reassign anchors
        self.anchors = []

        # save original cursor positon
        (line_bak, col_bak) = (vim.eval("line('.')"), vim.eval("col('.')"))
        vim.command("call cursor('1', '1')")
        pre_anchor = None
        pre_posi = 0
        while 1:
            posi = int(vim.eval("search('{0}', 'W')".format(self.defs)))
            if posi == 0: break
            new_anchor = Anchor(posi - pre_posi, pre_anchor)
            self.anchors.append(new_anchor)
            pre_posi = posi
            pre_anchor = new_anchor
        # restore cursor position
        vim.command("call cursor('{0}', '{1}')".format(line_bak, col_bak))

    # show or hide contents

    def render(self, string_list):
        for (anchor, content) in zip(self.anchors, string_list):
            # bind content and anchor
            anchor.bind(content)

            # escape '"' as a string
            for char in '"':
                content = content.replace(char, '\\'+char)

            # render content in vim
            abs_posi = anchor.getAbsPosition()
            command = 'silent! {0}put! ="{1}"'.format(abs_posi, content)
            # escape '|' and '"' as argument for 'put' command
            for char in '|"':
                command = command.replace(char, "\\"+char)
            # make 'modified' intact
            modified_bak = vim.eval('&modified')
            vim.command(command)
            vim.command('let &modified={0}'.format(modified_bak))

    def clear(self):
        for anchor in self.anchors:
            if anchor.size > 0:
                # clear content from buffer
                abs_posi = anchor.evalAbsPosition()
                range = "{0},{1}".format(abs_posi, abs_posi + anchor.size - 1)
                command = "silent! {0}delete _".format(range)
                # make 'modified' intact
                modified_bak = vim.eval('&modified')
                vim.command(command)
                vim.command('let &modified={0}'.format(modified_bak))
            else:
                pass

            # unbind content and anchor
            anchor.unbind()

    # cursor move

    def pointTo(self, offset):
        anchor = self.anchors[offset]
        position = anchor.getAbsPosition() + (anchor.size - 1)//2
        vim.command("normal {0}z.".format(position))


    # content formatter

    def commentize(self, str):
        output = self.prefix + self.filler * self.lineLen * 2 + "\\n"
        for l in str.split("\n"):
            output += "{0} {1}\\n".format(self.filler, l.encode('utf-8'))
        output += self.filler * self.lineLen * 2 + self.suffix + "\\n"
        return output

    def commentize_list(self, str_list):
        return [self.commentize(str) for str in str_list]


class Content():
    def read(self, index, amount):
        items = self.getItem(index, amount)
        return [i.content() for i in items]

    def getItem(self):
        pass

    def refresh(self):
        pass

    def ready(self):
        pass

class Item():
    def Content(self):
        pass

# Content: Book

class Book(Content):
    def __init__(self, path, session, option):
        self.fp      = open(path, 'r')
        self.items   = []
        self.lineLen = option['line_len']
        self.lineNum = option['line_num']

    def getItem(self, index, amount):
        output = []
        for i in range(index, index + amount):
            if i < len(self.items):
                output.append(self.items[i])
            else:
                option = {
                        'line_len':self.lineLen,
                        'line_num':self.lineNum,
                        }
                item = Page(self.fp, option)
                if item.content == "": break
                self.items.append(item)
                output.append(item)
        return output

class Page(Item):
    def __init__(self, fp, option):
        self.lineLen = option['line_len']
        self.lineNum = option['line_num']

        content = []
        line_loaded = 0
        while line_loaded <= self.lineLen:
            line = fp.readline().decode('utf-8')
            if not line: break
            line = line.rstrip('\r\n')
            if len(line) == 0: line = " "
            p = 0
            while p < len(line):
                content.append(line[p:p+self.lineNum])
                line_loaded += 1
                p += self.lineNum

        self.string = "\n".join(content)

    def content(self):
        return self.string

# Content: Weibo

class Weibo(Content):
    def __init__(self, session, option):
        self.items      = []
        self.token_info = self.loadSession(session)

    def reqAuthPage(self):
        url          = 'https://api.weibo.com/oauth2/authorize'
        client_id    = '1861844333'
        redirect_uri = 'https://api.weibo.com/oauth2/default.html'

        vim.command("let @+='{0}?client_id={1}&redirect_uri={2}'".format(url, client_id, redirect_uri))
        vim.command("echo 'open url in your clipboard'")

    def reqAccessToken(self, auth_code):
        client_id     = '1861844333'
        client_secret = '160fcb0ca75b22e35c644f8758e279c1'
        redirect_uri  = 'https://api.weibo.com/oauth2/default.html'

        url = 'https://api.weibo.com/oauth2/access_token'
        params = {
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
                'code': auth_code,
                }

        try:
            logging.debug("request: " + url + ' POST: ' + urllib.urlencode(params))
            res = urllib2.urlopen(url, urllib.urlencode(params))
            token_info = json.load(res)
            logging.debug("response: " + str(token_info))
            logging.debug("access_token: " + token_info['access_token'])
        except:
            # TODO: error handle
            logging.exception('')

        self.token_info = token_info
        return token_info

    def pullTweets(self):
        url = 'https://api.weibo.com/2/statuses/home_timeline.json'
        params = {
                'access_token': self.token_info['access_token'],
                'count': 20,
                'page': 1,
                }
        if len(self.items) != 0:
            params['max_id'] = self.items[-1].id - 1

        try:
            logging.debug("request: " + url + '?' + urllib.urlencode(params))
            res = urllib2.urlopen(url + '?' + urllib.urlencode(params))
            raw_timeline = json.load(res)
            logging.debug("response: " + str(raw_timeline))
        except:
            # TODO: error handle
            logging.exception('')

        for raw_tweet in raw_timeline['statuses']:
            self.items.append(Tweet(raw_tweet))

        return self.items

    def getItem(self, index, amount):
        while index + amount > len(self.items):
            self.pullTweets()
        return self.items[index:index+amount]

    def refresh(self):
        self.items = []

    def ready(self):
        if self.token_info.get('access_token', ''):
            return True
        else:
            return False

    def saveSession(self):
        return self.token_info 

    def loadSession(self, token_info):
        # TODO:validate if token expired
        return token_info

# Content: Twitter
class Twitter(Content):
    def __init__(self, session, option):
        # instance variables
        self.items        = []
        self.access_token = self.loadSession(session)

        # oauth2
        consumer_key    = "XmUMZJditvgoMPhomEv9Q"
        consumer_secret = "FcYAmssSLy5vGusg8yPjqc8zLqwOAUoQxwQuKdjDg"
        self.consumer = oauth2.Consumer(consumer_key, consumer_secret)

        if self.ready():
            token = oauth2.Token(self.access_token['oauth_token'], self.access_token['oauth_token_secret'])
            self.client = oauth2.Client(self.consumer, token)
        else:
            self.client = oauth2.Client(self.consumer)

    def reqAuthPage(self):
        request_token_url = 'https://api.twitter.com/oauth/request_token'
        authorize_url     = 'https://api.twitter.com/oauth/authorize'

        try:
            res, content = self.client.request(request_token_url, "GET")
        except:
            logging.exception('')

        request_token = dict(urlparse.parse_qsl(content))
        vim.command("let @+='{0}?oauth_token={1}'".format(authorize_url, request_token['oauth_token']))
        vim.command("echo 'open url in your clipboard'")

        self.request_token = request_token

    def reqAccessToken(self, PIN):
        access_token_url  = 'https://api.twitter.com/oauth/access_token'

        token = oauth2.Token(self.request_token['oauth_token'], self.request_token['oauth_token_secret'])
        token.set_verifier(PIN)
        self.client = oauth2.Client(self.consumer, token)

        res, content = self.client.request(access_token_url, "POST")

        # save Access Token
        self.access_token = dict(urlparse.parse_qsl(content))

        # set client's token to Access Token
        token = oauth2.Token(self.access_token['oauth_token'], self.access_token['oauth_token_secret'])
        self.client = oauth2.Client(self.consumer, token)

    def pullTweets(self):
        url = 'http://api.twitter.com/1.1/statuses/home_timeline.json'
        params = {
                'count': 20,
                }
        if len(self.items) != 0:
            params['max_id'] = self.items[-1].id - 1

        res, content = self.client.request(url + '?' + urllib.urlencode(params), "GET")
        try:
            raw_timeline = json.loads(content)
        except:
            logging.exception('')

        for raw_tweet in raw_timeline:
            self.items.append(Tweet(raw_tweet))

        return self.items

    def ready(self):
        if self.access_token.get('oauth_token', ''):
            return True
        else:
            return False

    def getItem(self, index, amount):
        while index + amount > len(self.items):
            self.pullTweets()
        return self.items[index:index+amount]

    def saveSession(self):
        return self.access_token

    def loadSession(self, access_token):
        return access_token

class Tweet(Item):
    def __init__(self, raw_tweet):
        self.id = long(raw_tweet['id'])
        self.author = raw_tweet['user']['screen_name']
        self.text = raw_tweet['text']

    def content(self):
        return self.author + ": " + self.text + "\n"

# Content: Douban

# Content: Facebook
