# ==============================
# 🔹 학습 모델 기반 승리 확률 예측
# ==============================
import torch
import torch.nn as nn
from sklearn.preprocessing import OneHotEncoder
import pickle

# 모델 정의
class MatchMLP(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )
    def forward(self, x):
        return self.model(x)

# 컬럼 (학습 때 사용한 순서)
cat_cols = [
    "championName", "individualPosition", "lane", "teamPosition", "role",
    "summoner1Id", "summoner2Id"
]

num_cols = [
    "kills", "deaths", "assists",
    "largestKillingSpree", "largestMultiKill",
    "doubleKills", "tripleKills", "quadraKills", "pentaKills",
    "totalDamageDealt", "totalDamageDealtToChampions", "totalDamageTaken",
    "damageSelfMitigated",
    "physicalDamageDealt", "magicDamageDealt", "trueDamageDealt",
    "physicalDamageDealtToChampions", "magicDamageDealtToChampions", "trueDamageDealtToChampions",
    "physicalDamageTaken", "magicDamageTaken", "trueDamageTaken",
    "timeCCingOthers", "totalTimeCCDealt",
    "goldEarned", "goldSpent", "itemsPurchased", "consumablesPurchased",
    "turretKills", "turretTakedowns", "turretsLost",
    "inhibitorKills", "inhibitorTakedowns", "inhibitorsLost",
    "baronKills", "dragonKills",
    "damageDealtToTurrets", "damageDealtToObjectives",
    "visionScore", "wardsPlaced", "wardsKilled", "visionWardsBoughtInGame",
    "longestTimeSpentLiving", "timePlayed"
]

st.subheader("AI 학습 모델 승리 확률 예측")

# 입력 UI
input_data = {}
st.write("⚡ 입력값 수정 후 예측 가능")

for col in num_cols:
    input_data[col] = st.number_input(col, value=0)

for col in cat_cols:
    input_data[col] = st.text_input(col, value="Unknown")

df_input = pd.DataFrame([input_data])

# OneHotEncoder 로드
if _exists("encoder.pkl"):
    with open("encoder.pkl", "rb") as f:
        encoder = pickle.load(f)
    X_cat = encoder.transform(df_input[cat_cols].fillna("Unknown"))
else:
    st.warning("encoder.pkl 파일이 없어 예측 불가")
    X_cat = None

X_num = df_input[num_cols].fillna(0).values

if X_cat is not None:
    X_input = torch.tensor(pd.concat([pd.DataFrame(X_num), pd.DataFrame(X_cat)], axis=1).values, dtype=torch.float32)

    # 모델 불러오기
    input_dim = X_input.shape[1]
    model = MatchMLP(input_dim)
    if _exists("match_model.pt"):
        model.load_state_dict(torch.load("match_model.pt"))
        model.eval()
    else:
        st.warning("match_model.pt 파일이 없어 예측 불가")
        model = None

    if model is not None and st.button("승리 확률 예측"):
        with torch.no_grad():
            y_pred = model(X_input)
            win_prob = y_pred.item() * 100
            st.success(f"승리 확률: {win_prob:.2f}%")
