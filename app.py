# app.py — ARAM 챔피언 대시보드 (아이콘: 챔피언/아이템/스펠/룬)
import os, re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ARAM PS Dashboard", layout="wide")

# ===== 파일 경로(리포 루트) =====
PLAYERS_CSV   = "aram_participants_clean_preprocessed.csv"       # 전처리 본판
ITEM_SUM_CSV  = "item_summary_with_icons_from_clean.csv"         # 전처리 아이템 요약
CHAMP_CSV     = "champion_icons.csv"                             # champion, champion_icon
RUNE_CSV      = "rune_icons.csv"                                 # rune_core, rune_core_icon, rune_sub, rune_sub_icon
SPELL_CSV     = "spell_icons.csv"                                # 스펠명, 아이콘 URL (헤더 자유)

DD_VERSION = "15.16.1"  # Data Dragon 폴백 버전

# ===== 유틸 =====
def _exists(path: str) -> bool:
    ok = os.path.exists(path)
    if not ok: st.warning(f"파일 없음: `{path}`")
    return ok

def _norm(x: str) -> str:
    return re.sub(r"\s+","", str(x)).strip().lower()

# ===== 로더 =====
@st.cache_data
def load_players(path: str) -> pd.DataFrame:
    if not _exists(path): st.stop()
    df = pd.read_csv(path)

    # 승패 정리
    if "win_clean" not in df.columns:
        if "win" in df.columns:
            df["win_clean"] = df["win"].astype(str).str.lower().isin(["true","1","t","yes"]).astype(int)
        else:
            df["win_clean"] = 0

    # 텍스트 정리
    text_cols = [c for c in df.columns if any(k in c.lower() for k in ["item","spell","rune","champion"])]
    for c in text_cols:
        df[c] = df[c].fillna("").astype(str).str.strip()

    return df

@st.cache_data
def load_item_summary(path: str, df_for_fallback: pd.DataFrame|None) -> pd.DataFrame:
    if _exists(path):
        g = pd.read_csv(path)
        need = {"item","icon_url","total_picks","wins","win_rate"}
        if not need.issubset(g.columns):
            st.warning(f"`{path}` 헤더 확인 필요 (기대: {sorted(need)}, 실제: {list(g.columns)})")
        if "item" in g.columns:
            g = g[g["item"].astype(str).str.strip() != ""]
        return g

    # 폴백: 참가자에서 즉석 집계(아이콘은 공란)
    if df_for_fallback is None:
        return pd.DataFrame(columns=["item","icon_url","total_picks","wins","win_rate"])
    item_cols = [c for c in df_for_fallback.columns
                 if ("item" in c.lower() and "name" in c.lower()) or re.fullmatch(r"item[0-6]_name", c)]
    stacks = []
    for c in item_cols:
        stacks.append(df_for_fallback[[c, "win_clean"]].rename(columns={c:"item"}))
    if not stacks:
        return pd.DataFrame(columns=["item","icon_url","total_picks","wins","win_rate"])
    u = pd.concat(stacks, ignore_index=True)
    u = u[u["item"].astype(str).str.strip() != ""]
    g = (u.groupby("item")
           .agg(total_picks=("item","count"), wins=("win_clean","sum"))
           .reset_index())
    g["win_rate"] = (g["wins"]/g["total_picks"]*100).round(2)
    g["icon_url"] = ""
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
    """스펠명(여러 형태) -> 아이콘 URL"""
    if not _exists(path): return {}
    df = pd.read_csv(path)
    cand_name = [c for c in df.columns if _norm(c) in {"spell","spellname","name","spell1_name_fix","spell2_name_fix","스펠","스펠명"}]
    cand_icon = [c for c in df.columns if _norm(c) in {"icon","icon_url","spellicon","spell_icon"} or "icon" in c.lower()]
    m = {}
    if cand_name and cand_icon:
        name_col, icon_col = cand_name[0], cand_icon[0]
        for n, i in zip(df[name_col].astype(str), df[icon_col].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    elif df.shape[1] >= 2:
        for n, i in zip(df.iloc[:,0].astype(str), df.iloc[:,1].astype(str)):
            m[_norm(n)] = i
            m[str(n).strip()] = i
    return m

# ===== 폴백 아이콘(룬/트리) =====
RUNE_CORE_ICON_FALLBACK = {
    "여진": "https://ddragon.canisback.com/img/perk-images/Styles/Resolve/VeteranAftershock/VeteranAftershock.png",
    "수호자": "https://ddragon.canisback.com/img/perk-images/Styles/Resolve/Guardian/Guardian.png",
    "정복자": "https://ddragon.canisback.com/img/perk-images/Styles/Precision/Conqueror/Conqueror.png",
    "치명적 속도": "https://ddragon.canisback.com/img/perk-images/Styles/Precision/LethalTempo/LethalTempoTemp.png",
    "집중 공격": "https://ddragon.canisback.com/img/perk-images/Styles/Precision/PressTheAttack/PressTheAttack.png",
    "기민한 발놀림": "https://ddragon.canisback.com/img/perk-images/Styles/Precision/FleetFootwork/FleetFootwork.png",
    "감전": "https://ddragon.canisback.com/img/perk-images/Styles/Domination/Electrocute/Electrocute.png",
    "어둠의 수확": "https://ddragon.canisback.com/img/perk-images/Styles/Domination/DarkHarvest/DarkHarvest.png",
    "콩콩이 소환": "https://ddragon.canisback.com/img/perk-images/Styles/Sorcery/SummonAery/SummonAery.png",
    "신비로운 유성": "https://ddragon.canisback.com/img/perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png",
}
RUNE_SUBTREE_ICON_FALLBACK = {
    "정밀": "https://ddragon.canisback.com/img/perk-images/Styles/7201_Precision.png",
    "지배": "https://ddragon.canisback.com/img/perk-images/Styles/7200_Domination.png",
    "마법": "https://ddragon.canisback.com/img/perk-images/Styles/7202_Sorcery.png",
    "결의": "https://ddragon.canisback.com/img/perk-images/Styles/7204_Resolve.png",
    "영감": "https://ddragon.canisback.com/img/perk-images/Styles/7203_Whimsy.png",
}

# ===== 스펠 별칭/폴백 =====
SPELL_ALIASES = {
    # 한글
    "점멸":"점멸","표식":"표식","눈덩이":"표식","유체화":"유체화","회복":"회복","점화":"점화",
    "정화":"정화","탈진":"탈진","방어막":"방어막","총명":"총명","순간이동":"순간이동",
    # 영문/변형
    "flash":"점멸","mark":"표식","snowball":"표식","ghost":"유체화","haste":"유체화",
    "heal":"회복","ignite":"점화","cleanse":"정화","exhaust":"탈진","barrier":"방어막",
    "clarity":"총명","teleport":"순간이동",
}
KOR_TO_DDRAGON = {
    "점멸":"SummonerFlash",
    "표식":"SummonerSnowball",
    "유체화":"SummonerHaste",
    "회복":"SummonerHeal",
    "점화":"SummonerDot",
    "정화":"SummonerBoost",
    "탈진":"SummonerExhaust",
    "방어막":"SummonerBarrier",
    "총명":"SummonerMana",
    "순간이동":"SummonerTeleport",
}
def standard_korean_spell(s: str) -> str:
    n = _norm(s)
    return SPELL_ALIASES.get(n, s)

def ddragon_spell_icon(s: str) -> str:
    kor = standard_korean_spell(s)
    key = KOR_TO_DDRAGON.get(kor)
    if not key: return ""
    return f"https://ddragon.leagueoflegends.com/cdn/{DD_VERSION}/img/spell/{key}.png"

# ===== 데이터 로드 =====
df        = load_players(PLAYERS_CSV)
item_sum  = load_item_summary(ITEM_SUM_CSV, df_for_fallback=df)
champ_map = load_champion_icons(CHAMP_CSV)
rune_maps = load_rune_icons(RUNE_CSV)
spell_map = load_spell_icons(SPELL_CSV)

ITEM_ICON_MAP = dict(zip(item_sum.get("item", []), item_sum.get("icon_url", [])))

# ===== 사이드바 =====
st.sidebar.title("ARAM PS Controls")
if "champion" not in df.columns or df["champion"].isna().all():
    st.error("데이터에 'champion' 컬럼이 없습니다.")
    st.stop()

champs = sorted(df["champion"].dropna().unique().tolist())
selected = st.sidebar.selectbox("Champion", champs, index=0 if champs else None)

# ===== 상단 요약 =====
dsel = df[df["champion"] == selected].copy()
games = len(dsel)
match_cnt_all = df["matchId"].nunique() if "matchId" in df.columns else len(df)
match_cnt_sel = dsel["matchId"].nunique() if "matchId" in dsel.columns else games
winrate = round(dsel["win_clean"].mean()*100, 2) if games else 0.0
pickrate = round((match_cnt_sel / match_cnt_all * 100), 2) if match_cnt_all else 0.0

c0, ctitle = st.columns([1, 5])
with c0:
    cicon = champ_map.get(selected, "")
    if cicon: st.image(cicon, width=64)
with ctitle:
    st.title(f"{selected}")

c1, c2, c3 = st.columns(3)
c1.metric("Games", f"{games}")
c2.metric("Win Rate", f"{winrate}%")
c3.metric("Pick Rate", f"{pickrate}%")

# ===== 아이템 추천 =====
st.subheader("Recommended Items")
item_cols = [c for c in dsel.columns
             if ("item" in c.lower() and "name" in c.lower()) or re.fullmatch(r"item[0-6]_name", c)]
if games and item_cols:
    stacks = [dsel[[c, "win_clean"]].rename(columns={c:"item"}) for c in item_cols]
    union = pd.concat(stacks, ignore_index=True)
    union = union[union["item"].astype(str).str.strip() != ""]
    top_items = (union.groupby("item")
                       .agg(total_picks=("item","count"), wins=("win_clean","sum"))
                       .reset_index())
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
    st.info("아이템 이름 컬럼이 없어 챔피언별 아이템 집계를 표시할 수 없습니다.")

# ===== 스펠 추천 (순서 무시 병합 + 아이콘 폴백) =====
st.subheader("Recommended Spell Combos")

def pick_spell_cols(df_):
    if {"spell1_u","spell2_u"}.issubset(df_.columns):
        return "spell1_u", "spell2_u"
    if {"spell1_name_fix","spell2_name_fix"}.issubset(df_.columns):
        return "spell1_name_fix", "spell2_name_fix"
    if {"spell1","spell2"}.issubset(df_.columns):
        return "spell1", "spell2"
    cands = [c for c in df_.columns if "spell" in c.lower()]
    return (cands[0], cands[1]) if len(cands) >= 2 else (None, None)

def resolve_spell_icon(name: str) -> str:
    if not name: return ""
    raw = str(name).strip()
    for k in (raw, _norm(raw), standard_korean_spell(raw), _norm(standard_korean_spell(raw))):
        if k in spell_map:
            return spell_map[k]
    return ddragon_spell_icon(raw)

s1, s2 = pick_spell_cols(dsel)
if games and s1 and s2:
    tmp = dsel[[s1, s2, "win_clean"]].copy()
    # 순서 무시: 표준화 후 정렬한 페어 키로 집계
    tmp[s1] = tmp[s1].apply(standard_korean_spell)
    tmp[s2] = tmp[s2].apply(standard_korean_spell)
    ordered = tmp.apply(lambda r: tuple(sorted([r[s1], r[s2]])), axis=1)
    tmp["pair_key"] = ordered
    g = (tmp.groupby("pair_key")
             .agg(games=("win_clean","count"), wins=("win_clean","sum"))
             .reset_index())
    g["spellA"] = g["pair_key"].apply(lambda k: k[0] if isinstance(k, tuple) and len(k)==2 else "")
    g["spellB"] = g["pair_key"].apply(lambda k: k[1] if isinstance(k, tuple) and len(k)==2 else "")
    g["win_rate"] = (g["wins"]/g["games"]*100).round(2)
    g = g.sort_values(["games","win_rate"], ascending=[False, False]).head(10)
    g["spellA_icon"] = g["spellA"].apply(resolve_spell_icon)
    g["spellB_icon"] = g["spellB"].apply(resolve_spell_icon)

    st.dataframe(
        g[["spellA_icon","spellA","spellB_icon","spellB","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "spellA_icon": st.column_config.ImageColumn("스펠1", width="small"),
            "spellB_icon": st.column_config.ImageColumn("스펠2", width="small"),
            "spellA":"스펠1 이름","spellB":"스펠2 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("스펠 컬럼을 찾지 못했습니다. (spell1_u/spell2_u 또는 spell1_name_fix/spell2_name_fix 또는 spell1/spell2 필요)")

# ===== 룬 추천 (아이콘 폴백 포함) =====
st.subheader("Recommended Rune Combos")
core_map = rune_maps.get("core", {})
sub_map  = rune_maps.get("sub", {})

def _rune_core_icon(name: str) -> str:
    return core_map.get(name) or RUNE_CORE_ICON_FALLBACK.get(name, "")

def _rune_sub_icon(name: str) -> str:
    return sub_map.get(name) or RUNE_SUBTREE_ICON_FALLBACK.get(name, "")

if games and {"rune_core","rune_sub"}.issubset(dsel.columns):
    ru = (dsel.groupby(["rune_core","rune_sub"])
               .agg(games=("win_clean","count"), wins=("win_clean","sum"))
               .reset_index())
    ru["win_rate"] = (ru["wins"]/ru["games"]*100).round(2)
    ru = ru.sort_values(["games","win_rate"], ascending=[False,False]).head(10)
    ru["rune_core_icon"] = ru["rune_core"].apply(_rune_core_icon)
    ru["rune_sub_icon"]  = ru["rune_sub"].apply(_rune_sub_icon)
    st.dataframe(
        ru[["rune_core_icon","rune_core","rune_sub_icon","rune_sub","games","wins","win_rate"]],
        use_container_width=True,
        column_config={
            "rune_core_icon": st.column_config.ImageColumn("핵심룬", width="small"),
            "rune_sub_icon":  st.column_config.ImageColumn("보조트리", width="small"),
            "rune_core":"핵심룬 이름","rune_sub":"보조트리 이름",
            "games":"게임수","wins":"승수","win_rate":"승률(%)"
        }
    )
else:
    st.info("룬 컬럼(rune_core, rune_sub)이 없습니다.")

# ===== 원본(선택 챔피언) =====
with st.expander("Raw rows (selected champion)"):
    st.dataframe(dsel, use_container_width=True)
