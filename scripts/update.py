#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "scripts" / "config.json").read_text(encoding="utf-8"))
DATA_FILE = ROOT / "data.json"
MODEL = CONFIG.get("model", "claude-haiku-4-5-20251001")


def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def rebuild_abstract(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def fetch_works(query, count):
    today = dt.date.today().isoformat()
    params = {
        "filter": f"to_publication_date:{today},has_abstract:true,type:article|preprint",
        "sort": "publication_date:desc",
        "per_page": str(count),
        "select": "id,doi,title,publication_date,primary_topic,"
                  "abstract_inverted_index,primary_location",
    }
    if query:
        params["search"] = query
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params["api_key"] = key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    works = http_json(url).get("results", [])
    items = []
    for w in works:
        loc = w.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name") or ""
        items.append({
            "id": w["id"].rsplit("/", 1)[-1],
            "title": w.get("title") or "Без названия",
            "abstract": rebuild_abstract(w.get("abstract_inverted_index"))[:3000],
            "topic_en": (w.get("primary_topic") or {}).get("display_name") or "",
            "url": w.get("doi") or loc.get("landing_page_url") or w["id"],
            "date": w.get("publication_date") or "",
            "source": src,
        })
    return items


PROMPT = """Ниже список научных статей (JSON). Для каждой статьи напиши:
- "summary": ОДНО предложение на русском (до 30 слов), простым языком: что сделали и что нашли;
- "topic": тема статьи по-русски, 1–4 слова.
Ответь ТОЛЬКО JSON-массивом вида [{"id": "...", "summary": "...", "topic": "..."}], без пояснений и без ```.

Статьи:
"""


def summarize(items):
    if not items:
        return {}
    payload = [{"id": i["id"], "title": i["title"], "abstract": i["abstract"],
                "topic_en": i["topic_en"]} for i in items]
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 3000,
        "messages": [{"role": "user",
                      "content": PROMPT + json.dumps(payload, ensure_ascii=False)}],
    }).encode("utf-8")
    resp = http_json("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    text = "".join(b.get("text", "") for b in resp.get("content", []))
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return {r["id"]: r for r in json.loads(text)}


def build_email(data):
    site = os.environ.get("SITE_URL", "")
    link = f' — <a href="{site}" style="color:#1F2A6B">открыть на сайте</a>' if site else ""
    parts = [f"""<div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;color:#1F2A6B">
<h1 style="font-family:Arial,sans-serif;font-size:22px;margin:0 0 4px">Свежие статьи</h1>
<p style="font-family:Arial,sans-serif;color:#5A6275;margin:0 0 24px;font-size:14px">
{dt.date.today().strftime('%d.%m.%Y')}{link}</p>"""]
    for t in data["topics"]:
        parts.append(f'<h2 style="font-family:Arial,sans-serif;font-size:16px;'
                     f'border-bottom:2px solid #F2D544;padding-bottom:6px">{html.escape(t["name"])}</h2>')
        for it in t["items"]:
            new = (' <span style="font-family:Arial,sans-serif;font-size:11px;'
                   'background:#1F2A6B;color:#fff;padding:1px 6px;border-radius:3px">новое</span>'
                   if it.get("new") else "")
            parts.append(f"""<div style="margin:0 0 18px">
<div style="font-family:Arial,sans-serif;font-size:12px"><span style="background:#F2D544;padding:1px 5px">{html.escape(it['topic'])}</span>{new}</div>
<p style="font-size:16px;line-height:1.5;margin:6px 0">{html.escape(it['summary'])}</p>
<div style="font-family:Arial,sans-serif;font-size:12px;color:#5A6275">{html.escape(it['title'])}<br>
{html.escape(it['source'])} {html.escape(it['date'])} — <a href="{html.escape(it['url'])}" style="color:#1F2A6B">читать статью</a></div>
</div>""")
    parts.append("</div>")
    return "".join(parts)


def send_email(data):
    user, pw, to = (os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "MAIL_TO"))
    user = (user or "").strip()
    pw = (pw or "").replace(" ", "").replace("\u00a0", "").strip()
    print(f"Проверка: адрес содержит @gmail.com: {'@gmail.com' in user}, длина пароля: {len(pw)}")
    if not (user and pw and to):
        print("SMTP не настроен — письмо пропущено")
        return
    new_count = sum(1 for t in data["topics"] for i in t["items"] if i.get("new"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Свежие статьи: {new_count} новых — {dt.date.today():%d.%m}"
    msg["From"], msg["To"] = user, to
    msg.attach(MIMEText(build_email(data), "html", "utf-8"))
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pw)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())
    print(f"Письмо отправлено: {to}")


def main():
    old = {}
    if DATA_FILE.exists():
        try:
            for t in json.loads(DATA_FILE.read_text(encoding="utf-8")).get("topics", []):
                for it in t["items"]:
                    old[it["id"]] = it
        except (json.JSONDecodeError, KeyError):
            pass
    count = int(CONFIG.get("count", 10))
    out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "topics": []}
    for topic in CONFIG["topics"]:
        items = fetch_works(topic.get("query", ""), count)
        fresh = [i for i in items if i["id"] not in old]
        sums = summarize(fresh)
        result = []
        for i in items:
            if i["id"] in old:
                prev = old[i["id"]]
                i["summary"], i["topic"], i["new"] = prev["summary"], prev["topic"], False
            else:
                s = sums.get(i["id"], {})
                i["summary"] = s.get("summary") or i["title"]
                i["topic"] = s.get("topic") or i["topic_en"]
                i["new"] = True
            i.pop("abstract", None)
            i.pop("topic_en", None)
            result.append(i)
        out["topics"].append({"name": topic["name"], "query": topic.get("query", ""),
                              "items": result})
        print(f"{topic['name']}: {len(result)} статей, новых {len(fresh)}")
    DATA_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if "--no-email" not in sys.argv:
        try:
            send_email(out)
        except Exception as e:
            print(f"Письмо не отправлено: {e}")


if __name__ == "__main__":
    main()
