import json, os, re, hashlib, urllib.request, urllib.parse, xml.etree.ElementTree as ET, html, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state.json'
SOURCES = ROOT / 'sources.json'
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
CHAT = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
HEADERS = {'User-Agent': 'NewsRadarRSS/1.0 (RSS reader; contact repository owner)'}
IMPORTANT = ['突发','重大','官宣','发布会','国务院','政策','地震','台风','预警','紧急','通报','全国人大','央行','财政部','外交部','首次','首发']
MASCOT = ['吉祥物','形象大使','卡通形象','文旅IP','文旅 IP','城市IP','城市 IP','官方IP','官方 IP','动漫IP','动漫 IP','潮玩','玩偶','公仔','萌宠','新形象','IP形象','IP 形象']

def request(url, data=None):
    req = urllib.request.Request(url, data=data, headers=HEADERS, )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()

def text(node, name):
    e = node.find(name)
    return ''.join(e.itertext()).strip() if e is not None else ''

def items(xml):
    root = ET.fromstring(xml)
    out=[]
    for entry in root.findall('.//item'):
        out.append({'title':html.unescape(text(entry,'title')), 'url':text(entry,'link'), 'date':text(entry,'pubDate')})
    if not out:
        ns={'a':'http://www.w3.org/2005/Atom'}
        for entry in root.findall('.//a:entry',ns):
            link=entry.find('a:link',ns)
            out.append({'title':html.unescape(text(entry,'{http://www.w3.org/2005/Atom}title')),'url':link.get('href','') if link is not None else '', 'date':text(entry,'{http://www.w3.org/2005/Atom}updated')})
    return out

def send(message):
    payload=urllib.parse.urlencode({'chat_id':CHAT,'text':message,'disable_web_page_preview':'true'}).encode()
    url='https://api.telegram.org/bot'+TOKEN+'/sendMessage'
    req=urllib.request.Request(url,data=payload,headers={'User-Agent':'NewsRadar/1.0'},timeout=20)
    with urllib.request.urlopen(req) as resp:
        result=json.load(resp)
    if not result.get('ok'): raise RuntimeError('Telegram rejected message')

def main():
    if not TOKEN or not CHAT: raise SystemExit('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Actions secrets')
    sources=json.loads(SOURCES.read_text(encoding='utf-8'))
    previous=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'initialized':False,'seen':[]}
    seen=set(previous.get('seen',[])); fresh=[]; failures=[]; fetched=0
    for source in sources:
        if not source.get('enabled',True): continue
        try:
            data=request(source['url']); entries=items(data); fetched+=1
            for entry in entries[:30]:
                title=re.sub(r'\s+',' ',entry['title']).strip()
                url=entry['url']
                if not title or not url: continue
                key=hashlib.sha256((source['name']+'|'+url).encode()).hexdigest()
                if key in seen: continue
                seen.add(key)
                mascot=any(word.lower() in title.lower() for word in MASCOT)
                important=any(word.lower() in title.lower() for word in IMPORTANT)
                if mascot or important:
                    fresh.append((key,source['name'],title,url,'吉祥物/IP' if mascot else '国内重要新闻'))
        except Exception as e:
            failures.append(source['name']+': '+str(e)[:150])
    # First run learns the existing feed items without alerting about old articles.
    if not previous.get('initialized',False):
        if fetched==0: raise SystemExit('No sources fetched; cannot initialize state: '+ '; '.join(failures))
        print('First run: establish baseline, do not send historical news')
    else:
        for _,source,title,url,category in fresh[:15]:
            msg=f'📰 NewsRadar | {category}\n来源：{source}\n{title[:250]}\n{url}'
            try:
                send(msg)
                time.sleep(0.5)
            except Exception as e:
                print('Telegram send failed:',str(e)[:180])
                raise
    STATE.write_text(json.dumps({'initialized':True,'seen':list(seen)[-3000:]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Sources OK: {fetched}/{len(sources)}; matched: {len(fresh)}; failures: {failures}')

if __name__=='__main__': main()
