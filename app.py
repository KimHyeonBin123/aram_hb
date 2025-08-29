# app.py — ARAM 챔피언 대시보드 + AI 조합 분석
import os, re
import pandas as pd
import streamlit as st
import requests
import json
import uuid

# ==============================
# ✅ 네이버 Clova 생성형 AI 설정
# ==============================
ACCESS_KEY = "ncp_iam_BPAMKR2DUA9LsitOQiAq"
SECRET_KEY = "ncp_iam_BPKMKRM9ooQXpjc8M2i61r6CrfyzEo4k3H"
API_URL = "https://clovastudio.stream.ntruss.com/testapp/v1/chat-completions/HCX-003"

# ==============================
# Streamlit 페이지 설정
# ==============================
st.set_page_config(page_title="ARAM PS Dashboard + AI 분석", layout="wide")

# ==============================
# 파일 경로
# ==============================
PLAYERS_CSV   = "aram_participants_with_icons_superlight.csv"
ITEM_SUM_CSV  = "item_summary_with_icons.csv"
CHAMP_CSV     = "champion_icons.csv"
RUNE_CSV      = "rune_icons.csv"
SPELL_CSV     = "spell_icons.csv"

DD_VERSION = "15.16.1"  # Data Dragon 폴백

# ==============================
# 유틸
# ==============================
def _exists(path: str) -> bool:
    ok = os.path.exists(path)
    if not ok:
        st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x: str) -> str:
    return re.sub(r"\s+", "", str(x)).strip().lower()

# ==============================
# 데이터 로더
# ==============================
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path): st.stop()
    df = pd.read_csv(path, encoding='utf-8')
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0
    for c in [c for c in df.columns if re.fullmatch(r"item[0-6]_name", c)]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    for c in ["spell1","spell2","spell1_name_fix","spell2_name_fix","rune_core","rune_sub","champion"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()
    return df

@st.cache_data
def load_item_summary(path: str) -> pd.DataFrame:
    if not _exists(path): return pd.DataFrame()
    g = pd.read_csv(path)
    need = {"item","icon_url","total_picks","wins","win_rate"}
    if not need.issubset(g.columns):
        st.warning(f"`{path}` 헤더 확인 필요")
    if "item" in g.columns:
        g = g[g["item"].astype(str).str.strip() != ""]
    return g

@st.cache_data
def load_champion_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    name_col = next((c for c in ["champion","Champion","championName"] if c in df.columns), None)
    icon_col = next((c for c in ["champion_icon","icon","icon_url"] if c in df.columns), None)
    if not name_col or not icon_col: return {}
    df[name_col] = df[name_col].astype(str).str.strip()
    return dict(zip(df[name_col], df[icon_col]))

@st.cache_data
def load_rune_icons(path: str) -> dict:
    if not _exists(path): return {"core": {}, "sub": {}, "shards": {}}
    df = pd.read_csv(path)
    core_map, sub_map, shard_map = {}, {}, {}
    if "rune_core" in df.columns:
        ic = "rune_core_icon" if "rune_core_icon" in df.columns else None
        if ic: core_map = dict(zip(df["rune_core"].astype(str), df[ic].astype(str)))
    if "rune_sub" in df.columns:
        ic = "rune_sub_icon" if "rune_sub_icon" in df.columns else None
        if ic: sub_map = dict(zip(df["rune_sub"].astype(str), df[ic].astype(str)))
    if "rune_shard" in df.columns:
        ic = "rune_shard_icon" if "rune_shard_icon" in df.columns else ("rune_shards_icons" if "rune_shards_icons" in df.columns else None)
        if ic: shard_map = dict(zip(df["rune_shard"].astype(str), df[ic].astype(str)))
    return {"core": core_map, "sub": sub_map, "shards": shard_map}

@st.cache_data
def load_spell_icons(path: str) -> dict:
    if not _exists(path): return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if _norm(c) in {"icon","icon_url"} or "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        name_col, icon_col = cand_name[0], cand_icon[0]
        for n, i in zip(df[name_col].astype(str), df[icon_col].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    else:
        if df.shape[1] >= 2:
            for n, i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)):
                m[_norm(n)] = i
                m[str(n).strip()] = i
    return m

# ==============================
# 데이터 로드
# ==============================
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV)
champ_map = load_champion_icons(CHAMP_CSV)
rune_maps = load_rune_icons(RUNE_CSV)
spell_map = load_spell_icons(SPELL_CSV)
ITEM_ICON_MAP = dict(zip(item_sum.get("item", []), item_sum.get("icon_url", [])))

# ==============================
# 사이드바
# ==============================
st.sidebar.title("ARAM PS Controls")
champs = sorted(df["champion"].dropna().unique().tolist()) if "champion" in df.columns else []
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ==============================
# 상단 요약
# ==============================
dsel = df[df["champion"] == selected].copy() if len(champs) else df.head(0).copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df.columns else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round((match_cnt_sel / match_cnt_all * 100), 2) if match_cnt_all else 0.0

c0, ctitle = st.columns([1,5])
with c0:
    cicon = champ_map.get(selected, "")
    if cicon:
        st.image(cicon, width=64)
with ctitle:
    st.title(f"{selected}")

c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ==============================
# 아이템 추천
# ==============================
st.subheader("Recommended Items")
if games and any(re.fullmatch(r"item[0-6]_name", c) for c in dsel.columns):
    stacks = []
    for c in [c for c in dsel.columns if re.fullmatch(r"item[0-6]_name", c)]:
        stacks.append(dsel[[c, "win_clean"]].rename(columns={c: "item"}))
    union = pd.concat(stacks, ignore_index=True)
    union = union[union["item"].astype(str).str.strip() != ""]
    top_items = (
        union.groupby("item")
        .agg(total_picks=("item","count"), wins=("win_clean","sum"))
        .reset_index()
    )
    top_items["win_rate"] = (top_items["wins"]/top_items["total_picks"]*100).round(2)
    top_items["icon_url"] = top_items["item"].map(ITEM_ICON_MAP)
    top_items = top_items.sort_values(["total_picks","win_rate"], ascending=[False, False]).head(20)

    st.dataframe(
        top_items[["icon_url","item","total_picks","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "icon_url": st.column_config.ImageColumn("아이콘", width="small"),
            "item": "아이템", "total_picks": "픽수", "wins": "승수", "win_rate": "승률(%)"
        }
    )
else:
    st.info("아이템 이름 컬럼(item0_name~item6_name)이 없어 챔피언별 아이템 집계를 만들 수 없습니다.")

