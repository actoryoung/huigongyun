import pandas as pd
from rapidfuzz import process, score_cutoff


class LocalPriceTable:
    def __init__(self, xlsx_path: str):
        # 读取从利驰或dq123导出的标准价格库
        self.df = pd.read_excel(xlsx_path)  # 列名设为: brand, model, price

    def get_price(self, target_brand: str, target_spec: str):
        # 1. 先过滤出同品牌的数据
        brand_df = self.df[self.df["brand"].str.upper() == target_brand.upper()]
        if brand_df.empty:
            return None, 0.0  # 品牌未匹配到

        # 2. 利用系统自带的 RapidFuzz 对型号进行模糊匹配（防止空格、斜杠导致对不上）
        choices = brand_df["model"].tolist()
        match = process.extractOne(target_spec, choices, score_cutoff=80)

        if match:
            matched_model = match[0]
            price = brand_df[brand_df["model"] == matched_model]["price"].values[0]
            return matched_model, float(price)
        return None, 0.0
