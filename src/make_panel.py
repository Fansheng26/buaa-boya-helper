"""Offline pipeline: parse the captured data, compute conflicts, render out/boya.html."""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _boot  # noqa: E402
from util import banner, log  # noqa: E402

# 第 1 周周一（来源于教务首页「第7周 10/19~10/25」）
WEEK1_MONDAY = datetime.date(2026, 9, 7)

# 节次起始时间（分钟），每节 45 分钟。全部来自实际作息表，并与教务首页
# 「学习日程」显示的 6-7节 14:00-15:35、8-9节 15:50-17:25、11-14节 19:00-22:15 一致。
PERIOD_START = {
    1: 8 * 60, 2: 8 * 60 + 50, 3: 9 * 60 + 50, 4: 10 * 60 + 40, 5: 11 * 60 + 30,
    6: 14 * 60, 7: 14 * 60 + 50, 8: 15 * 60 + 50, 9: 16 * 60 + 40,
    10: 17 * 60 + 30, 11: 19 * 60, 12: 19 * 60 + 50, 13: 20 * 60 + 40, 14: 21 * 60 + 30,
}
PERIOD_LEN = 45

CAT_COLORS = {
    "安全健康": "#e0523c",
    "德育": "#2f6fd0",
    "美育": "#7b53c9",
    "劳动教育": "#2f8a5b",
    "智育": "#b07d18",
    "体育": "#cf6a1f",
    "其他方面": "#6b7280",
    "其他": "#6b7280",
}
DEFAULT_COLOR = "#6b7280"


def kv_lines(text):
    out = {}
    for line in (text or "").split("\n"):
        line = line.strip()
        if "：" in line:
            k, v = line.split("：", 1)
            out[k.strip()] = v.strip()
    return out


def parse_dt(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_weeks(text):
    """'王佳星[2-4周,6-10周]' -> (name, {2,3,4,6..10})"""
    m = re.search(r"\[([^\]]*)\]", text or "")
    weeks = set()
    if m:
        for part in m.group(1).replace("，", ",").split(","):
            part = part.strip()
            rng = re.match(r"(\d+)\s*-\s*(\d+)\s*周", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if "单" in part:
                    weeks |= set(range(a, b + 1, 2))
                elif "双" in part:
                    weeks |= set(range(a + (1 if a % 2 else 2), b + 1, 2))
                else:
                    weeks |= set(range(a, b + 1))
                continue
            one = re.match(r"(\d+)\s*周", part)
            if one:
                weeks.add(int(one.group(1)))
    name = re.sub(r"\[[^\]]*\]", "", text or "").strip()
    return name, weeks


def parse_periods(text):
    m = re.match(r"(\d+)\s*-\s*(\d+)\s*节", text or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)\s*节", text or "")
    if m:
        return int(m.group(1)), int(m.group(1))
    return None


def load_schedule():
    path = _boot.DATA / "byxt_grid_term.json"
    if not path.exists():
        return []
    grid = json.loads(path.read_text(encoding="utf-8"))
    courses, seen = [], set()
    for col in grid:
        weekday = col["idx"] + 1
        for blob in col.get("courses", []):
            for block in re.split(r"\n(?=（[本研]）)", blob):
                lines = [x.strip() for x in block.split("\n") if x.strip()]
                if len(lines) < 4:
                    continue
                name = re.sub(r"^（[本研]）", "", lines[0]).strip()
                code = lines[1] if re.match(r"^[A-Z0-9]{4,}$", lines[1]) else ""
                ti = next((i for i, l in enumerate(lines) if "[" in l and "周" in l), None)
                if ti is None:
                    continue
                teacher, weeks = parse_weeks(lines[ti])
                location = lines[ti + 1] if ti + 1 < len(lines) else ""
                periods = None
                for line in lines[ti + 1:]:
                    periods = parse_periods(line)
                    if periods:
                        break
                if not periods:
                    continue
                key = (name, code, weekday, periods, tuple(sorted(weeks)), location)
                if key in seen:
                    continue
                seen.add(key)
                courses.append({
                    "name": name, "code": code, "teacher": teacher,
                    "weekday": weekday, "periods": periods, "weeks": weeks,
                    "location": location,
                })
    return courses


def load_boya():
    path = _boot.DATA / "boya_rows_all.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    out = []
    for r in rows:
        if len(r) < 10:
            continue
        info, tm, win, aud = kv_lines(r[3]), kv_lines(r[4]), kv_lines(r[6]), kv_lines(r[5])
        start, end = parse_dt(tm.get("开始")), parse_dt(tm.get("结束"))
        if not start or not end:
            continue
        m = re.match(r"\s*(\d+)\s*/\s*(\d+)", r[8] or "")
        out.append({
            "status": (r[0] or "").strip(),
            "name": (r[1] or "").strip(),
            "category": (r[2] or "").strip(),
            "location": info.get("地点", ""),
            "teacher": info.get("教师", ""),
            "college": info.get("学院", ""),
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "campus": aud.get("校区", ""),
            "pick_mode": win.get("选课方式", ""),
            "pick_start": win.get("选课开始", ""),
            "pick_end": win.get("选课结束", ""),
            "pick_cancel": win.get("退选截止", ""),
            "enrolled": int(m.group(1)) if m else None,
            "max": int(m.group(2)) if m else None,
            "_start": start,
            "_end": end,
        })
    return out


def week_of(d):
    return (d - WEEK1_MONDAY).days // 7 + 1


def find_conflicts(course, schedule):
    s, e = course["_start"], course["_end"]
    hits = []
    for c in schedule:
        if c["weekday"] != s.isoweekday():
            continue
        if week_of(s.date()) not in c["weeks"]:
            continue
        p1, p2 = c["periods"]
        m1, m2 = PERIOD_START.get(p1), PERIOD_START.get(p2)
        if m1 is None or m2 is None:
            continue
        day = s.date()
        cs = datetime.datetime.combine(day, datetime.time(m1 // 60, m1 % 60))
        ce = datetime.datetime.combine(day, datetime.time(m2 // 60, m2 % 60)) + datetime.timedelta(minutes=PERIOD_LEN)
        if s < ce and cs < e:
            hits.append({"name": c["name"], "periods": f"{p1}-{p2}节",
                         "teacher": c["teacher"], "location": c["location"]})
    return hits


def short_cat(cat):
    """'博雅课程-安全健康' -> '安全健康'；未知/空类型统一归到「其他」，不会因为新类型崩掉。"""
    c = (cat or "").split("-", 1)[1] if "-" in (cat or "") else (cat or "")
    c = c.strip()
    return c or "其他"


def build_items():
    schedule = load_schedule()
    boya = load_boya()
    log(f"  课表课程 {len(schedule)} 条，博雅课程 {len(boya)} 条")

    items = []
    for b in boya:
        if b["status"] not in ("预告", "可选"):
            continue
        if "沙河" in b["location"]:
            continue
        full = (b["max"] is not None and b["enrolled"] is not None and b["enrolled"] >= b["max"])
        if b["status"] == "可选":
            state = "可选·已满" if full else "可选·未满"
        else:
            state = "预告"
        hits = find_conflicts(b, schedule)
        cat = short_cat(b["category"])
        items.append({
            "status": b["status"], "state": state, "full": full,
            "name": b["name"], "category": b["category"], "cat": cat,
            "color": CAT_COLORS.get(cat, DEFAULT_COLOR),
            "location": b["location"], "teacher": b["teacher"], "college": b["college"],
            "start": b["start"], "end": b["end"], "campus": b["campus"],
            "pick_mode": b["pick_mode"], "pick_start": b["pick_start"],
            "pick_end": b["pick_end"], "pick_cancel": b["pick_cancel"],
            "enrolled": b["enrolled"], "max": b["max"],
            "conflict": hits, "free": not hits,
            "date": b["_start"].strftime("%Y-%m-%d"),
            "weekday": b["_start"].isoweekday(),
        })
    items.sort(key=lambda x: (x["date"], x["full"], x["start"], x["name"]))
    return items, schedule


HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>博雅选课助手 · 不冲突课程</title>
<style>
:root{--bg:#f4f6fa;--card:#fff;--ink:#161a22;--sub:#687085;--line:#e3e7f0;
--green:#0b8a4b;--greenbg:#e6f6ec;--red:#c62828;--redbg:#fdecec;
--blue:#1a5fd0;--bluebg:#e8f0fe;--amber:#a35b00;--amberbg:#fff3e0;}
*{box-sizing:border-box}
body{margin:0;font:14px/1.62 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--ink)}
header{padding:22px 28px 18px;background:linear-gradient(120deg,#12386e,#1a5fd0);color:#fff}
h1{margin:0 0 6px;font-size:19px;font-weight:600;letter-spacing:.2px}
.meta{font-size:12.5px;opacity:.82}
.stats{display:flex;gap:9px;margin-top:14px;flex-wrap:wrap}
.stat{background:rgba(255,255,255,.14);border-radius:9px;padding:6px 13px;font-size:12.5px}
.stat b{font-size:17px;margin-right:4px;font-weight:700}
.bar{position:sticky;top:0;z-index:9;background:rgba(244,246,250,.95);
backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:10px 28px;
display:flex;gap:7px;flex-wrap:wrap;align-items:center}
.lbl{font-size:12px;color:var(--sub);margin:0 2px 0 10px}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:4px 12px;
cursor:pointer;font-size:12.5px;color:#374151;transition:.15s;user-select:none}
.chip:hover{border-color:#b9c0d0}
.chip.on{background:#1a5fd0;border-color:#1a5fd0;color:#fff}
input[type=search]{margin-left:auto;border:1px solid var(--line);border-radius:999px;
padding:5px 14px;font-size:13px;min-width:190px;outline:none}
main{padding:16px 28px 70px;max-width:1180px;margin:0 auto}
.day{margin:22px 0 10px;font-size:13.5px;font-weight:700;color:#3b4254;
display:flex;align-items:center;gap:10px}
.day .line{flex:1;height:1px;background:var(--line)}
.card{position:relative;background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:12px 16px 12px 18px;margin-bottom:9px;
display:grid;grid-template-columns:1fr auto;gap:2px 16px;overflow:hidden;
transition:.15s}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c)}
.card:hover{box-shadow:0 4px 16px rgba(20,30,60,.08);transform:translateY(-1px)}
.card.busy{opacity:.62}
.card.busy:hover{opacity:.9}
.head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:3px}
.cat{font-size:11.5px;font-weight:700;color:#fff;background:var(--c);
padding:2px 9px;border-radius:6px;letter-spacing:.3px}
.st{font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:6px;border:1px solid}
.st.free{color:var(--green);background:var(--greenbg);border-color:#b7e2c6}
.st.full{color:var(--amber);background:var(--amberbg);border-color:#f0cfa0}
.st.pre{color:var(--blue);background:var(--bluebg);border-color:#bcd2f7}
.name{font-size:15px;font-weight:650;letter-spacing:.1px}
.rows{margin-top:5px;display:grid;grid-template-columns:auto 1fr;gap:2px 10px;
font-size:13px;color:#333a4a;align-items:baseline}
.k{color:var(--sub);font-size:12.5px;white-space:nowrap}
.t{font-variant-numeric:tabular-nums}
.pick{color:#7a4a00}
.note{font-size:12px;font-weight:600}
.note.soon{color:var(--blue)}
.note.live{color:var(--green)}
.note.over{color:var(--sub)}
.warn{color:var(--red)}
.tag{font-size:11.5px;padding:1px 8px;border-radius:6px;background:#f0f2f7;color:#4b5563}
.tag.ok{background:var(--greenbg);color:var(--green);font-weight:600}
.tag.hold{background:var(--amberbg);color:var(--amber);font-weight:600}
.tag.no{background:var(--redbg);color:var(--red);font-weight:600}
.right{text-align:right;font-size:12px;color:var(--sub);white-space:nowrap;
display:flex;flex-direction:column;justify-content:center;gap:3px}
.cap{font-weight:700;font-size:14px;font-variant-numeric:tabular-nums}
.cap.free{color:var(--green)}.cap.full{color:var(--amber)}
.empty{text-align:center;color:var(--sub);padding:70px 0}
.hintbox{max-width:1180px;margin:14px auto 0;padding:0 28px}
.hintbox:empty{display:none}
.hint{background:var(--amberbg);border:1px solid #f0cfa0;color:#7a4a00;
border-radius:10px;padding:10px 14px;font-size:13px}
</style></head><body>
<header>
  <h1>博雅选课助手 · 与课表不冲突的课程</h1>
  <div class="meta">数据时间 __GENERATED__ ｜ 只保留「预告 / 可选」且地点不含「沙河」的课程 ｜ 冲突判定基于本学期课表的实际周次与节次</div>
  <div class="stats" id="stats"></div>
</header>
<div class="bar">
  <span class="lbl">视图</span>
  <div class="chip on" data-k="view" data-v="free">只看不冲突</div>
  <div class="chip" data-k="view" data-v="all">全部</div>
  <div class="chip" data-k="view" data-v="busy">只看冲突</div>
  <div class="chip" data-k="view" data-v="upcoming">即将开抢</div>
  <span class="lbl">状态</span>
  <div class="chip on" data-k="state" data-v="all">全部</div>
  <div class="chip" data-k="state" data-v="可选·未满">可选·未满</div>
  <div class="chip" data-k="state" data-v="可选·已满">可选·已满</div>
  <div class="chip" data-k="state" data-v="预告">预告</div>
  <span class="lbl">类别</span>
  <div id="cats" style="display:flex;gap:7px;flex-wrap:wrap"></div>
  <input type="search" id="q" placeholder="搜索课程 / 教师 / 地点">
</div>
<div id="hint" class="hintbox"></div>
<main id="list"></main><script>
const DATA = __DATA__;
const S = {view:'free', state:'all', cat:'all', q:''};
const el = id => document.getElementById(id);
const WD = '日一二三四五六';
const now = new Date();

function fmtRange(d){
  const s = new Date(d.start.replace(' ','T'));
  const e = new Date(d.end.replace(' ','T'));
  const day = `${d.start.slice(5,10)} 周${WD[s.getDay()]}`;
  return `${day} ${d.start.slice(11)}–${d.end.slice(11)}`;
}
function pickInfo(d){
  if(!d.pick_start || !d.pick_end) return {range:'—', status:'', lead:'', cls:'', openNow:false};
  const ps = new Date(d.pick_start.replace(' ','T'));
  const pe = new Date(d.pick_end.replace(' ','T'));
  const st = new Date(d.start.replace(' ','T'));
  let status, cls;
  if(now < ps){
    const h = (ps-now)/3600000;
    status = h > 48 ? `未开始 · 还有 ${Math.round(h/24)} 天` : `未开始 · 还有 ${Math.round(h)} 小时`;
    cls = 'soon';
  } else if(now > pe){
    status = '已截止';
    cls = 'over';
  } else {
    const h = (pe-now)/3600000;
    status = h > 48 ? `进行中 · 剩 ${Math.round(h/24)} 天` : `进行中 · 剩 ${Math.max(1,Math.round(h))} 小时`;
    cls = 'live';
  }
  const leadDays = (st-pe)/86400000;
  const lead = leadDays >= 1
    ? `截止早于开课 ${leadDays.toFixed(1)} 天`
    : `截止早于开课 ${Math.max(1, Math.round(leadDays*24))} 小时`;
  return {range:`${d.pick_start.slice(5,16)} → ${d.pick_end.slice(5,16)}`,
          status, lead, cls, openNow: now>=ps && now<=pe};
}
function card(d){
  const cap = d.max ? `${d.enrolled}/${d.max}` : '';
  const stCls = d.state==='预告' ? 'pre' : (d.full ? 'full' : 'free');
  const pick = pickInfo(d);
  const conflict = d.conflict.length
    ? `<span class="tag no">冲突：${d.conflict.map(c=>c.name+' '+c.periods).join('；')}</span>`
    : (d.full ? `<span class="tag hold">无冲突 · 已满</span>` : `<span class="tag ok">无冲突</span>`);
  return `<div class="card ${d.free?'':'busy'}" style="--c:${d.color}">
    <div>
      <div class="head">
        <span class="cat">${d.cat}</span>
        <span class="st ${stCls}">${d.state}</span>
        ${conflict}
      </div>
      <div class="name">${d.name}</div>
      <div class="rows">
        <span class="k">上课</span><span class="t">${fmtRange(d)}</span>
        <span class="k">选课</span><span class="t">${pick.range}</span>
        <span class="k"></span><span class="note ${pick.cls}">${pick.status} · ${pick.lead}</span>
        <span class="k">地点</span><span class="t">${d.location}</span>
        <span class="k">开课</span><span class="t">${d.teacher} · ${d.college}</span>
      </div>
    </div>
    <div class="right">
      <div class="cap ${d.full?'full':'free'}">${cap}</div>
      <div>${d.pick_mode}</div>
    </div>
  </div>`;
}
function render(){
  const q = S.q.trim().toLowerCase();
  const rows = DATA.filter(d => {
    if(S.view==='free' && !d.free) return false;
    if(S.view==='busy' && d.free) return false;
    if(S.view==='upcoming'){
      const ps = d.pick_start ? new Date(d.pick_start.replace(' ','T')) : null;
      if(!ps || !(ps > now) || d.state !== '预告') return false;
    }
    if(S.state!=='all' && d.state!==S.state) return false;
    if(S.cat!=='all' && d.cat!==S.cat) return false;
    if(q && !(d.name+d.teacher+d.location+d.college+d.cat).toLowerCase().includes(q)) return false;
    return true;
  });
  const groups = {};
  rows.forEach(d => (groups[d.date] = groups[d.date] || []).push(d));
  const days = Object.keys(groups).sort();
  el('list').innerHTML = days.length ? days.map(day => {
    const ds = groups[day];
    const wd = WD[new Date(day+'T00:00:00').getDay()];
    return `<div class="day">${day.slice(5)} 周${wd} · ${ds.length} 门<span class="line"></span></div>`
      + ds.map(card).join('');
  }).join('') : `<div class="empty">${S.state==='可选·未满'
      ? '目前没有「可选且未满」的课程 —— 这类课基本一放出来就被抢完了，可以切到「预告」或「即将开抢」盯着。'
      : '没有符合条件的课程'}</div>`;

  el('stats').innerHTML =
    `<div class="stat"><b>${DATA.length}</b>门候选</div>
     <div class="stat"><b>${DATA.filter(d=>d.free).length}</b>门无冲突</div>
     <div class="stat"><b>${DATA.filter(d=>d.state==='可选·未满').length}</b>门可选且未满</div>
     <div class="stat"><b>${DATA.filter(d=>d.state==='预告').length}</b>门预告</div>
     <div class="stat"><b>${DATA.filter(d=>d.state==='预告' && d.pick_start && new Date(d.pick_start.replace(' ','T'))>now).length}</b>门即将开抢</div>`;

  const openable = DATA.filter(d=>d.free && d.state==='可选·未满').length;
  el('hint').innerHTML = openable ? '' :
    `<div class="hint">当前没有「可选且未满」的课 —— 博雅基本一放出来就被抢光。
     可以切到 <b>即将开抢</b> 盯着预告课，或过一阵再刷新（有人退课会重新放出名额）。</div>`;
}
const cats = [...new Set(DATA.map(d=>d.cat))];
const catColor = {}; DATA.forEach(d=>catColor[d.cat]=d.color);
el('cats').innerHTML = `<div class="chip on" data-k="cat" data-v="all">全部</div>` +
  cats.map(c=>`<div class="chip" data-k="cat" data-v="${c}" style="border-left:4px solid ${catColor[c]}">${c}</div>`).join('');

document.querySelectorAll('.chip').forEach(c => c.onclick = () => {
  const k = c.dataset.k;
  document.querySelectorAll(`.chip[data-k="${k}"]`).forEach(x => x.classList.toggle('on', x===c));
  S[k] = c.dataset.v; render();
});
el('q').oninput = e => { S.q = e.target.value; render(); };
render();
</script></body></html>
"""


def write_atomic(path, text):
    """先写临时文件再替换，避免小组件读到写了一半的 JSON。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    banner("生成面板")
    items, schedule = build_items()
    free = [x for x in items if x["free"]]
    free_open = [x for x in free if x["state"] == "可选·未满"]
    log(f"  候选 {len(items)} 门｜无冲突 {len(free)} 门｜可选且未满 {len([x for x in items if x['state']=='可选·未满'])} 门")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False)).replace("__GENERATED__", now)
    out = _boot.OUT / "boya.html"
    write_atomic(out, html)
    log(f"  已生成 {out}")

    # 给桌面小组件用的数据
    write_atomic(_boot.OUT / "panel.json",
                 json.dumps({"generated": now, "items": items}, ensure_ascii=False))

    for x in free:
        log(f"    [OK] {x['start'][5:16]} {x['cat']:6} {x['name'][:30]} [{x['state']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
