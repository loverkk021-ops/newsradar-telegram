import json, os, re, hashlib, urllib.request, urllib.parse, xml.etree.ElementTree as ET, html, time, datetime, email.utils
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state.json'
SOURCES = ROOT / 'sources.json'
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
CHAT = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
HEADERS = {'User-Agent': 'NewsRadarRSS/1.0 (RSS reader; contact repository owner)'}
IMPORTANT = ['突发','重大','官宣','发布会','国务院','政策','地震','台风','预警','紧急','通报','全国人大','央行','财政部','外交部','首次','首发']
MASCOT = ['吉祥物','形象大使','卡通形象','文旅IP','文旅 IP','城市IP','城市 IP','官方IP','官方 IP','动漫IP','动漫 IP','潮玩','玩偶','公仔','萌宠','新形象','IP形象','IP 形象']
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

def is_today(date_str):
    if not date_str:
        return False
    try:
        published = email.utils.parsedate_to_datetime(date_str)
        if published.tzinfo is None:
            published = published.replace(tzinfo=datetime.timezone.utc)
        today = datetime.datetime.now(BEIJING_TZ).date()
        return published.astimezone(BEIJING_TZ).date() == today
    except (TypeError, ValueError, OverflowError):
        return False
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
    payload = urllib.parse.urlencode({'chat_id': CHAT, 'text': message, 'disable_web_page_preview': 'true'}).encode()
    url = 'https://api.telegram.org/bot' + TOKEN + '/sendMessage'
    req = urllib.request.Request(url, data=payload, headers={'User-Agent': 'NewsRadar/1.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.load(resp)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected message')

def main():
    if os.environ.get('TEST_TELEGRAM') == '1':
        send('✅ NewsRadar 测试成功！Telegram 新闻推送通道正常。')
        print('Telegram test message sent successfully')
        return
       
    if not TOKEN or not CHAT: raise SystemExit('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Actions secrets')
    sources=json.loads(SOURCES.read_text(encoding='utf-8'))
    previous=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'initialized':False,'seen':[]}
    seen=set(previous.get('seen',[])); fresh=[]; failures=[]; fetched=0
    seen_titles=set(previous.get('seen_titles', []))
    for source in sources:
        if not source.get('enabled',True): continue
        try:
            data=request(source['url']); entries=items(data); fetched+=1
           for entry in entries[:30]:
                title=re.sub(r'\s+',' ',entry['title']).strip()
                url=entry['url']
                if not title or not url: continue
                if not is_today(entry.get('date', '')):
                    continue
                key=hashlib.sha256((source['name']+'|'+url).encode()).hexdigest()
                if key in seen: continue
                seen.add(key)
            title_key = hashlib.sha256(
                    re.sub(r'\W+', '', title.lower()).encode('utf-8')
                ).hexdigest()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                mascot=any(word.lower() in title.lower() for word in MASCOT)
                important=any(word.lower() in title.lower() for word in IMPORTANT)
                if mascot or important or source['name'] in ('央视新闻', '人民日报', '中国新闻网', '新华社'):
                   fresh.append((key,source['name'],title,url,'吉祥物/IP' if '吉祥物' in source['name'] else '新闻快讯'))
        except Exception as e:
            failures.append(source['name']+': '+str(e)[:150])
    # First run learns the existing feed items without alerting about old articles.
    if not previous.get('initialized',False):
        if fetched==0: raise SystemExit('No sources fetched; cannot initialize state: '+ '; '.join(failures))
        print('First run: establish baseline, do not send historical news')
    else:
        for _,source,title,url,category in fresh:
            msg=f'📰 NewsRadar | {category}\n来源：{source}\n{title[:250]}\n{url}'
            try:
                send(msg)
                time.sleep(0.5)
            except Exception as e:
                print('Telegram send failed:',str(e)[:180])
                raise
    STATE.write_text(json.dumps({'initialized':True,'seen':list(seen)[-3000:],'seen_titles':list(seen_titles)[-3000:]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Sources OK: {fetched}/{len(sources)}; matched: {len(fresh)}; failures: {failures}')

if __name__=='__main__': main()
