# -*- coding: utf-8 -*-
"""
build_site.py — Gerador automático da "Biblioteca da Família" (Steam).
Roda no GitHub Actions (servidor, sem CORS). Lê STEAM_API_KEY do ambiente
(Secret do repositório), consulta a Steam Web API + Store API e gera index.html.

Seções: Ranking (por nº de jogos) · Stats · Wishlist da família (por demanda) ·
        Jogando agora (últimas 2 semanas).
"""
import os, json, time, html, urllib.request

KEY = os.environ.get("STEAM_API_KEY", "").strip()
CC, LANG = "br", "portuguese"
GEN_DATE = time.strftime("%d/%m/%Y")

MEMBERS = [
    {"nick": "Zeylon",  "real": "Thiago",  "steamid": "76561197974461365"},
    {"nick": "DarkLou", "real": "",        "steamid": "76561198028049882"},
    {"nick": "Tteuz",   "real": "Matheus", "steamid": "76561198022007693"},
    {"nick": "Primata", "real": "",        "steamid": "76561198139240184"},
    {"nick": "Henso",   "real": "",        "steamid": "76561197991671841"},
    {"nick": "Menezes", "real": "",        "steamid": "76561198141356141"},
]

# ---------------------------------------------------------------- HTTP helper
def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (familia-steam-bot)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def appdetails(appid):
    d = get_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc={CC}&l={LANG}&filters=basic,price_overview,release_date")
    time.sleep(0.4)
    return (d or {}).get(str(appid), {}) or {}

def appreviews_pct(appid):
    d = get_json(f"https://store.steampowered.com/appreviews/{appid}?json=1&language=all&purchase_type=all&num_per_page=0")
    time.sleep(0.2)
    q = (d or {}).get("query_summary", {}) or {}
    tot = q.get("total_reviews", 0)
    return round(100 * q.get("total_positive", 0) / tot) if tot else None

# ---------------------------------------------------------------- 1) OWNED
owned_set, name_by, play_total, play_2w, recent_who, count_by = set(), {}, {}, {}, {}, {}
for m in MEMBERS:
    d = get_json(f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key={KEY}&steamid={m['steamid']}&include_appinfo=true&include_played_free_games=true&format=json")
    games = ((d or {}).get("response") or {}).get("games", []) if d else []
    count_by[m["nick"]] = len(games)
    for g in games:
        a = g["appid"]
        owned_set.add(a)
        if g.get("name"):
            name_by[a] = g["name"]
        play_total[a] = play_total.get(a, 0) + g.get("playtime_forever", 0)
        tw = g.get("playtime_2weeks", 0)
        if tw:
            play_2w[a] = play_2w.get(a, 0) + tw
            recent_who.setdefault(a, []).append((m["nick"], tw))

membros = sorted(
    [{"nick": m["nick"], "real": m["real"], "steamid": m["steamid"], "jogos": count_by.get(m["nick"], 0)} for m in MEMBERS],
    key=lambda x: -x["jogos"])
bruto = sum(count_by.values())
unicos = len(owned_set)
dup = bruto - unicos

# ---------------------------------------------------------------- 2) WISHLIST
wl_votes = {}
for m in MEMBERS:
    d = get_json(f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?key={KEY}&steamid={m['steamid']}")
    items = ((d or {}).get("response") or {}).get("items", []) if d else []
    for it in items:
        a = it.get("appid")
        if not a or a in owned_set:
            continue
        wl_votes.setdefault(a, []).append(m["nick"])

wishlist = []
for a, who in wl_votes.items():
    dd = appdetails(a)
    if not dd.get("success"):
        continue
    data = dd["data"]
    p = data.get("price_overview") or {}
    coming = bool((data.get("release_date") or {}).get("coming_soon"))
    wishlist.append({
        "appid": a, "name": data.get("name", ""), "n": len(who), "who": who,
        "disc": p.get("discount_percent", 0),
        "fin": p.get("final_formatted", ""), "orig": p.get("initial_formatted", ""),
        "pct": (None if coming else appreviews_pct(a)),
        "coming": coming, "free": bool(data.get("is_free")),
        "img": (data.get("header_image", "") or "").split("?")[0],
    })
wishlist.sort(key=lambda x: (-x["n"], -x["disc"], -(x["pct"] or 0)))
maxN = max([x["n"] for x in wishlist], default=1)

# ---------------------------------------------------------------- 3) JOGANDO AGORA (2 semanas)
recent = []
for a, mins in sorted(play_2w.items(), key=lambda kv: -kv[1])[:20]:
    dd = appdetails(a)
    data = dd.get("data", {}) if dd.get("success") else {}
    who = sorted(recent_who.get(a, []), key=lambda x: -x[1])
    recent.append({
        "appid": a, "name": name_by.get(a) or data.get("name", ""),
        "hrs": round(mins / 60, 1),
        "who": [{"nick": n, "hrs": round(t / 60, 1)} for n, t in who],
        "img": (data.get("header_image", "") or "").split("?")[0],
    })

DATA = {
    "membros": membros,
    "stats": {"unicos": unicos, "bruto": bruto, "duplicados": dup, "membros": len(MEMBERS)},
    "wishlist": wishlist, "wlmax": maxN,
    "wlstats": {"total": len(wishlist), "multi": len([x for x in wishlist if x["n"] >= 2]),
                "promo": len([x for x in wishlist if x["disc"] > 0])},
    "recent": recent,
    "recentHoras": round(sum(x["hrs"] for x in recent)),
}

# ---------------------------------------------------------------- HTML
TPL = r'''<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Biblioteca da Família · Steam</title><style>
:root{--panel:#16202d;--panel2:#2a475e;--line:#32404e;--txt:#c7d5e0;--txt2:#8f98a0;--blue:#66c0f4;--blue-d:#417a9b;--green:#a4d007;--green2:#beee11;--gold:#f0c14b;--purple:#b48ee8}
*{box-sizing:border-box}body{margin:0;font-family:"Motiva Sans",Arial,sans-serif;background:linear-gradient(180deg,#1b2838,#171a21 320px,#171a21);color:var(--txt);line-height:1.5}
a{color:var(--blue);text-decoration:none}a:hover{color:#fff}.wrap{max-width:1120px;margin:0 auto;padding:0 18px}
header.hero{padding:46px 0 26px;text-align:center}header.hero h1{margin:0 0 6px;font-size:34px;color:#fff;font-weight:700}
header.hero p{margin:0;color:var(--txt2);font-size:15px}.badge-fam{display:inline-block;margin-bottom:14px;padding:5px 14px;border:1px solid var(--blue-d);border-radius:20px;color:var(--blue);font-size:12px;letter-spacing:1.5px;text-transform:uppercase}
.stats{display:flex;flex-wrap:wrap;gap:14px;justify-content:center;margin:26px 0 10px}.stat{background:linear-gradient(135deg,#2a475e,#1b2838);border:1px solid var(--line);border-radius:6px;padding:16px 22px;min-width:140px;text-align:center}
.stat .n{font-size:30px;font-weight:700;color:#fff}.stat .l{font-size:12px;color:var(--txt2);text-transform:uppercase;letter-spacing:1px;margin-top:3px}.stat.green .n{color:var(--green2)}.stat.pink .n{color:var(--purple)}
section{margin:44px 0}h2{font-size:13px;text-transform:uppercase;letter-spacing:2px;color:var(--blue);border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:18px;font-weight:700}
h2 .sub{color:var(--txt2);text-transform:none;letter-spacing:0;font-weight:400;font-size:12px;margin-left:8px}
.rank-row{display:flex;align-items:center;gap:14px;padding:11px 14px;margin-bottom:9px;background:var(--panel);border:1px solid var(--line);border-radius:6px;transition:.15s}
.rank-row:hover{border-color:var(--blue-d);transform:translateX(3px)}.rank-pos{font-size:20px;font-weight:700;color:var(--txt2);width:34px;text-align:center;flex:none}
.rank-row.top1 .rank-pos{color:var(--gold)}.rank-row.top2 .rank-pos{color:#cdd6df}.rank-row.top3 .rank-pos{color:#cd7f32}
.rank-name{width:130px;flex:none;font-weight:700;color:#fff;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rank-name small{display:block;font-weight:400;color:var(--txt2);font-size:11px}
.rank-bar{flex:1;background:#0e151c;border-radius:4px;height:24px;overflow:hidden}.rank-fill{height:100%;background:linear-gradient(90deg,var(--blue-d),var(--blue));border-radius:4px;display:flex;align-items:center;justify-content:flex-end;min-width:42px}
.rank-row.top1 .rank-fill{background:linear-gradient(90deg,#b58a1d,var(--gold))}.rank-val{font-weight:700;color:#0e151c;font-size:13px;padding-right:9px}.rank-pct{width:54px;flex:none;text-align:right;color:var(--txt2);font-size:12px}
.recs{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.rec{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden;display:flex;flex-direction:column;transition:.15s;position:relative}
.rec:hover{border-color:var(--blue);box-shadow:0 4px 18px rgba(0,0,0,.4)}
.cap{width:100%;aspect-ratio:460/215;background:linear-gradient(135deg,#2a475e,#1b2838);position:relative;overflow:hidden}
.cap img{width:100%;height:100%;object-fit:cover;display:block}
.rec .body{padding:12px 13px;display:flex;flex-direction:column;gap:7px;flex:1}.rec .nm{font-weight:700;color:#fff;font-size:14px;line-height:1.25}
.rec .meta{display:flex;align-items:center;gap:8px;margin-top:auto;flex-wrap:wrap}
.disc{background:var(--green);color:#1b2838;font-weight:700;font-size:13px;padding:3px 7px;border-radius:3px}
.price{font-size:13px}.price .o{color:var(--txt2);text-decoration:line-through;margin-right:6px;font-size:11px}.price .f{color:var(--green2);font-weight:700}
.review{font-size:11px;color:var(--blue)}
.wl-demand{position:absolute;top:8px;left:8px;background:rgba(180,142,232,.96);color:#1b1024;font-weight:700;font-size:12px;padding:3px 9px;border-radius:12px;z-index:2}
.wl-who{font-size:11px;color:var(--purple)}
.hrs-badge{position:absolute;top:8px;left:8px;background:rgba(102,192,244,.96);color:#08131c;font-weight:700;font-size:12px;padding:3px 9px;border-radius:12px;z-index:2}
.soon{background:var(--purple);color:#1b1024;font-weight:700;font-size:12px;padding:3px 7px;border-radius:3px}.freeb{background:#5c7e10;color:#fff;font-weight:700;font-size:12px;padding:3px 7px;border-radius:3px}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:auto}.chip{background:#0e151c;border:1px solid var(--line);color:var(--txt2);border-radius:10px;font-size:10px;padding:1px 7px}
.tier{font-size:16px;color:#fff;margin:24px 0 12px;display:flex;align-items:center;gap:10px}.tier .gcount{font-size:11px;color:var(--txt2);background:#0e151c;border:1px solid var(--line);border-radius:12px;padding:2px 9px;font-weight:400}.tier.big{font-size:18px}.tier .flame{color:var(--gold)}
footer{border-top:1px solid var(--line);margin-top:48px;padding:24px 0 50px;color:var(--txt2);font-size:12px;text-align:center}
@media(max-width:560px){.rank-name{width:92px}.rank-pct{display:none}header.hero h1{font-size:26px}}
</style></head><body><div class="wrap">
<header class="hero"><div class="badge-fam">Compartilhamento Familiar Steam</div><h1>Biblioteca da Família</h1>
<p>Atualizado automaticamente · o que a família joga, tem e deseja</p><div class="stats" id="stats"></div></header>
<section><h2>Jogando agora <span class="sub">o que a família mais jogou nas últimas 2 semanas</span></h2><div class="recs" id="recent"></div></section>
<section><h2>Ranking de contribuição <span class="sub">por total de jogos na biblioteca</span></h2><div id="ranking"></div></section>
<section><h2>Wishlist da família <span class="sub">jogos que os membros querem — do mais desejado ao menos</span></h2><div id="wishlist"></div></section>
<footer>Atualizado em __DATE__ · Fonte: Steam Web API (GetOwnedGames + IWishlistService) + Steam Store API<br>Página gerada automaticamente toda semana.</footer>
</div><script>
const DATA=__DATA__;const $=s=>document.querySelector(s);
const st=DATA.stats,ws=DATA.wlstats;
$('#stats').innerHTML=[['',st.unicos,'Jogos da família',1],['',ws.total,'Na wishlist','pink'],['',DATA.recentHoras,'Horas (2 sem)',0],['',st.membros,'Membros',0]].map(([k,n,l,g])=>`<div class="stat ${g===1?'green':(g==='pink'?'pink':'')}"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');
function cap(img,name){return `<div class="cap">${img?`<img src="${img}" loading="lazy" alt="" onerror="this.remove()">`:''}</div>`;}
// JOGANDO AGORA
$('#recent').innerHTML=(DATA.recent||[]).map(r=>`<a class="rec" href="https://store.steampowered.com/app/${r.appid}" target="_blank"><span class="hrs-badge">▶ ${r.hrs}h</span>${cap(r.img,r.name)}<div class="body"><div class="nm">${(r.name||'').replace(/</g,'&lt;')}</div><div class="chips">${r.who.map(w=>`<span class="chip">${w.nick} ${w.hrs}h</span>`).join('')}</div></div></a>`).join('') || '<p style="color:var(--txt2)">Ninguém jogou nas últimas 2 semanas.</p>';
// RANKING
const mx=Math.max(...DATA.membros.map(m=>m.jogos),1);
$('#ranking').innerHTML=DATA.membros.map((m,i)=>{const pct=Math.round(100*m.jogos/mx),sh=DATA.stats.bruto?Math.round(100*m.jogos/DATA.stats.bruto):0,tc=i<3?`top${i+1}`:'',sub=m.real?`<small>${m.real}</small>`:'';return `<div class="rank-row ${tc}"><div class="rank-pos">${i+1}º</div><div class="rank-name"><a href="https://steamcommunity.com/profiles/${m.steamid}" target="_blank">${m.nick}</a>${sub}</div><div class="rank-bar"><div class="rank-fill" style="width:${pct}%"><span class="rank-val">${m.jogos}</span></div></div><div class="rank-pct">${sh}%</div></div>`;}).join('');
// WISHLIST por tier
function membrosLabel(n){return n===1?'1 membro':`${n} membros`;}
function price(r){if(r.coming)return '<span class="soon">Em breve</span>';if(r.free&&!r.fin)return '<span class="freeb">Grátis</span>';if(r.disc>0)return `<span class="disc">-${r.disc}%</span><span class="price"><span class="o">${r.orig}</span><span class="f">${r.fin}</span></span>`;if(r.fin)return `<span class="price"><span class="f">${r.fin}</span></span>`;return '';}
function wcard(r){return `<a class="rec" href="https://store.steampowered.com/app/${r.appid}" target="_blank"><span class="wl-demand">♥ ${r.n}x</span>${cap(r.img,r.name)}<div class="body"><div class="nm">${(r.name||'').replace(/</g,'&lt;')}</div><div class="wl-who">${membrosLabel(r.n)}: ${r.who.join(', ')}</div>${r.pct!=null?`<div class="review">▲ ${r.pct}% positivas</div>`:''}<div class="meta">${price(r)}</div></div></a>`;}
let wh='';for(let t=DATA.wlmax;t>=1;t--){const g=DATA.wishlist.filter(x=>x.n===t);if(!g.length)continue;const big=t>=3?'big':'';const titulo=t===1?'1 membro quer':`${t} membros querem`;wh+=`<h3 class="tier ${big}">${big?'<span class="flame">★</span> ':''}${titulo} <span class="gcount">${g.length} ${g.length>1?'jogos':'jogo'}</span></h3><div class="recs">${g.map(wcard).join('')}</div>`;}
$('#wishlist').innerHTML=wh||'<p style="color:var(--txt2)">Wishlist vazia ou privada.</p>';
</script></body></html>'''

out = TPL.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__DATE__", GEN_DATE)
with open("index.html", "w", encoding="utf-8") as f:
    f.write(out)
print(f"index.html gerado: {len(out)} bytes | unicos={unicos} wishlist={len(wishlist)} recent={len(recent)}")
