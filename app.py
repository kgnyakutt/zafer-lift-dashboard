import pandas as pd
import numpy as np
import re
import streamlit as st
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import warnings
warnings.filterwarnings("ignore")

# Sayfa Yapılandırması
st.set_page_config(page_title="Zafer Lift - Üretim ve Performans Panosu", layout="wide")

# --- GÜVENLİK KİLİDİ ---
def sifre_kontrol():
    def sifre_girildi():
        if st.session_state["sifre_kutusu"] == "0228":
            st.session_state["sifre_dogru"] = True
        else:
            st.session_state["sifre_dogru"] = False

    if st.session_state.get("sifre_dogru", False):
        return True

    st.markdown("### 🔒 Zafer Lift - Güvenli Giriş")
    st.text_input("Panele erişmek için şifrenizi girip Enter'a basın:", type="password", on_change=sifre_girildi, key="sifre_kutusu")
    if "sifre_dogru" in st.session_state and not st.session_state["sifre_dogru"]:
        st.error("❌ Hatalı Şifre! Lütfen tekrar deneyin.")
    return False

if not sifre_kontrol():
    st.stop()

st.title("🚀 Zafer Lift Makine - Üretim ve Operatör Performans Panosu")
st.markdown("Bu pano, Google Sheets bulut altyapısıyla canlı olarak senkronize edilmiştir.")

# --- ZORLUK HARİTASI VE ÇARPANLAR ---
ZORLUK_HARITASI = {
    "EYP1Ç": 1.0, "HYM2": 1.0, "HYM1": 1.0, "HYM2EAP": 1.0, "HR": 1.0,
    "EYP2": 1.0, "EYP3": 1.0, "EYP1": 1.0, "EAP2": 1.0, "EYP1U": 1.0,
    "EYP4": 1.0, "EYP1S12": 1.0, "EYP1S11": 1.0, "EAP1": 1.0, "EYP1T": 1.0,
    "EEP3": 1.0, "EYP1H": 1.0, "EYP1A": 1.0, "EEP2": 1.0, "EEP1": 1.0,
    "PYM157ÖZEL": 1.0, "HYM2T": 1.0, "HYM4": 1.0, "EYP2H": 1.0
}
MAKSIMUM_CARPAN_KAPASITE = 2.0   
MAKSIMUM_CARPAN_M2 = 1.3       
MAKSIMUM_CARPAN_TEKNIK = 1.5   
MAKASLI_KODLAR = ["EYP1Ç", "EYP2", "EYP3", "EYP1", "EAP2", "EYP1U", "EYP4", "EYP1S12", "EYP1S11", "EAP1", "EYP1T", "EEP3", "EYP1H", "EYP1A", "EEP2", "EEP1", "PYM157ÖZEL", "EYP2H", "HR"]

def urun_makasli_mi(urun):
    urun_str = str(urun).upper().replace("İ", "I").replace("ı", "I")
    if "MAKASLI" in urun_str: return True
    return any(kod in urun_str for kod in MAKASLI_KODLAR)

# --- KENAR ÇUBUĞU DEPARTMAN YÖNETİMİ ---
st.sidebar.header("🏢 Atölye / Departman Seçimi")
secilen_departman = st.sidebar.radio(
    "Hangi departmanın verilerini incelemek istiyorsunuz?",
    ["Kaynak / İmalat Atölyesi", "Hidrolik Atölyesi", "Montaj Ekibi"]
)

# ==========================================
# 1. KAYNAK ATÖLYESİ VERİ İŞLEME FONKSİYONU
# ==========================================
@st.cache_data(ttl=5)
def veri_isle_kaynak():
    sheet_url = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=0"
    try: df = pd.read_csv(sheet_url)
    except: df = pd.DataFrame()
    if df.empty: return df
    
    def urun_normalize(deger):
        if pd.isna(deger): return deger
        s = str(deger).strip().upper().replace("İ", "I").replace("ı", "I") 
        return re.sub(r'[\s\.\-]+', '', s)

    def dinamik_zorluk(urun):
        if pd.isna(urun): return 1.0
        urun_str = str(urun).upper()
        if urun_str in ZORLUK_HARITASI: return ZORLUK_HARITASI[urun_str]
        if any(kod in urun_str for kod in ["EYP", "HYM", "EEP", "EAP"]): return 2.5
        if "ÖZEL" in urun_str or "OZEL" in urun_str: return 6.5 if "MAKASLI" in urun_str else (6.0 if "KOLONLU" in urun_str else 3.0)
        return 1.5

    def kapasite_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '': return 1.0
        s = str(deger).lower().replace(',', '.')
        match = re.search(r'[\d\.]+', s)
        if match:
            sayi = float(match.group())
            return sayi / 1000.0 if sayi > 50 or "kg" in s else sayi
        return 1.0

    def metrekare_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '': return 1.0
        s = str(deger).lower().replace(' ', '').replace(',', '.')
        parcalar = re.split(r'[\*x]', s)
        if len(parcalar) == 2:
            try:
                en = float(re.search(r'[\d\.]+', parcalar[0]).group())
                boy = float(re.search(r'[\d\.]+', parcalar[1]).group())
                return (en * boy) / 1_000_000.0
            except: pass
        match = re.search(r'[\d\.]+', s)
        if match: 
            val = float(match.group())
            return val / 1_000_000.0 if val > 100 else val
        return 1.0
        
    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Model", "Çelik Durumu (1/0)", "Kapasite", "Platform Ebat mm", "Platform Ebat (m2)", "Teknik Puan", "Başlangıç", "Bitiş", "Tezgah", "Operatörler", "Üretim Adedi", "Tel Fonk", "Bekleme Süresi (Gün)"]
    df = df[[col for col in hedef_sutunlar if col in df.columns]]

    df["Model"] = df["Model"].apply(urun_normalize)
    df["Tezgah"] = df.get("Tezgah", pd.Series(["Makaslı-1"]*len(df))).fillna("Makaslı-1")
    df["Ham_Zorluk"] = df["Model"].apply(dinamik_zorluk)
    df["Çelik Çarpanı"] = pd.to_numeric(df.get("Çelik Durumu (1/0)", 0.0), errors='coerce').fillna(0.0) + 1.0
    df["Kapasite_G"] = df.get("Kapasite", pd.Series([1.0]*len(df))).apply(kapasite_ayikla).replace(0, 1.0)
    
    if "Platform Ebat (m2)" not in df.columns and "Platform Ebat mm" in df.columns: df["Platform Ebat (m2)"] = df["Platform Ebat mm"]
    df["Ebat_G"] = df.get("Platform Ebat (m2)", pd.Series([1.0]*len(df))).apply(metrekare_ayikla).replace(0, 1.0)
    df["Teknik Puan"] = pd.to_numeric(df.get("Teknik Puan", 1.0), errors='coerce').fillna(1.0)
    
    df["Toplam Süre (Gün)"] = (pd.to_datetime(df["Bitiş"], dayfirst=True, errors='coerce') - pd.to_datetime(df["Başlangıç"], dayfirst=True, errors='coerce')).dt.days
    df["Bekleme Süresi (Gün)"] = pd.to_numeric(df.get("Bekleme Süresi (Gün)", 0.0), errors='coerce').fillna(0.0)
    df["Net Üretim Süresi (Gün)"] = (df["Toplam Süre (Gün)"] - df["Bekleme Süresi (Gün)"]).apply(lambda x: max(x, 1.0) if pd.notna(x) else 1.0)

    min_kap, max_kap = df["Kapasite_G"].min(), df["Kapasite_G"].max()
    df["Normalize_Kapasite"] = 1.0 if max_kap == min_kap else 1.0 + ((df["Kapasite_G"] - min_kap) / (max_kap - min_kap)) * (MAKSIMUM_CARPAN_KAPASITE - 1.0)
    
    makasli_mask = df["Model"].apply(urun_makasli_mi)
    min_m2, max_m2 = (df.loc[makasli_mask, "Ebat_G"].min(), df.loc[makasli_mask, "Ebat_G"].max()) if makasli_mask.any() else (1.0, 1.0)
    df["Normalize_Ebat"] = df.apply(lambda row: 1.0 + ((row["Ebat_G"] - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0) if urun_makasli_mi(row["Model"]) and max_m2 > min_m2 else 1.0, axis=1)
    df["Normalize_Teknik"] = 1.0 + ((df["Teknik Puan"] - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
    
    min_hz, max_hz = df["Ham_Zorluk"].min(), df["Ham_Zorluk"].max()
    df["Zorluk Katsayısı"] = 1.0 if max_hz == min_hz else 1.0 + ((df["Ham_Zorluk"] - min_hz) / (max_hz - min_hz)) * 9.0

    df["Ham_İş_Yükü"] = df['Zorluk Katsayısı'] * df['Normalize_Kapasite'] * df['Çelik Çarpanı'] * df['Normalize_Ebat'] * df['Normalize_Teknik']
    df["Günlük_Hız"] = df["Ham_İş_Yükü"] / df["Net Üretim Süresi (Gün)"]
    medyan_hiz = df["Günlük_Hız"].median()
    df["Zaman Verimlilik Çarpanı"] = (df["Günlük_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    
    df['Operatörler'] = df['Operatörler'].fillna('').astype(str)
    df['Kişi Sayısı'] = df['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    return df

# ==========================================
# 2. HİDROLİK ATÖLYESİ VERİ İŞLEME
# ==========================================
@st.cache_data(ttl=5)
def veri_isle_hidrolik():
    sheet_url_hidrolik = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=248930197"
    try: df = pd.read_csv(sheet_url_hidrolik)
    except: df = pd.DataFrame() 
    if df.empty: return df

    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Başlangıç", "Bitiş", "Tezgah", "Operatörler", "Üretim Adedi", "Yağ Tankı(lt)", "Motor(kW)"]
    df = df[[col for col in hedef_sutunlar if col in df.columns]]

    def parse_sayisal(val):
        if pd.isna(val) or str(val).strip() == '': return 1.0
        nums = re.findall(r"[\d\.]+", str(val).replace(',', '.'))
        valid = [float(n) for n in nums if n.count('.') <= 1]
        return max(valid) if valid else 1.0

    df["Tank_Val"] = df.get("Yağ Tankı(lt)", pd.Series([1.0]*len(df))).apply(parse_sayisal)
    df["Motor_Val"] = df.get("Motor(kW)", pd.Series([1.0]*len(df))).apply(parse_sayisal)
    df["Üretim Adedi"] = pd.to_numeric(df.get("Üretim Adedi", 1), errors='coerce').fillna(1.0)

    df["Net Üretim Süresi (Gün)"] = (pd.to_datetime(df.get("Bitiş"), dayfirst=True, errors='coerce') - pd.to_datetime(df.get("Başlangıç"), dayfirst=True, errors='coerce')).dt.days.apply(lambda x: max(x, 1.0) if pd.notna(x) else 1.0)
    df["Bekleme Süresi (Gün)"] = 0.0 

    min_t, max_t = df["Tank_Val"].min(), df["Tank_Val"].max()
    df["Normalize_Tank"] = 1.0 if max_t == min_t else 1.0 + ((df["Tank_Val"] - min_t) / (max_t - min_t)) * (1.5 - 1.0)
    min_m, max_m = df["Motor_Val"].min(), df["Motor_Val"].max()
    df["Normalize_Motor"] = 1.0 if max_m == min_m else 1.0 + ((df["Motor_Val"] - min_m) / (max_m - min_m)) * (2.0 - 1.0)

    df["Ham_İş_Yükü"] = df["Normalize_Tank"] * df["Normalize_Motor"] * df["Üretim Adedi"]
    df["Günlük_Hız"] = df["Ham_İş_Yükü"] / df["Net Üretim Süresi (Gün)"]
    medyan_hiz = df["Günlük_Hız"].median()
    df["Zaman Verimlilik Çarpanı"] = (df["Günlük_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    df['Operatörler'] = df['Operatörler'].fillna('').astype(str)
    df['Kişi Sayısı'] = df['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    return df

# ==========================================
# 3. MONTAJ EKİBİ VERİ İŞLEME (İLİŞKİSEL + HARİTA)
# ==========================================
@st.cache_data(ttl=86400) # Lokasyon sorgularını yormamak için 1 gün önbellekte tutar
def mesafe_hesapla_api(hedef_sehir):
    if pd.isna(hedef_sehir) or str(hedef_sehir).strip() == "": return 10.0
    try:
        geolocator = Nominatim(user_agent="zafer_lift_app")
        merkez = geolocator.geocode("Turgutlu, Manisa, Turkey")
        hedef = geolocator.geocode(f"{hedef_sehir}, Turkey")
        if merkez and hedef:
            return geodesic((merkez.latitude, merkez.longitude), (hedef.latitude, hedef.longitude)).km
    except: pass
    return 50.0 # API yanıt vermezse varsayılan değer

@st.cache_data(ttl=5)
def veri_isle_montaj():
    sheet_url_montaj = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=857495736"
    try: df_m = pd.read_csv(sheet_url_montaj)
    except: df_m = pd.DataFrame()
    if df_m.empty: return df_m

    df_m.columns = df_m.columns.str.strip()
    hedef_sutunlar_m = ["Sipariş No", "Başlangıç", "Bitiş", "Tezgah", "Operatörler", "Üretim Adedi", "Montaj Yeri", "Model"]
    df_m = df_m[[col for col in hedef_sutunlar_m if col in df_m.columns]]
    df_m["Sipariş No"] = df_m["Sipariş No"].astype(str).str.strip()
    
    # 3.1. Kaynak Tablosundan Makine Spesifikasyonlarını Çekme (LEFT JOIN)
    df_kaynak = veri_isle_kaynak()
    if not df_kaynak.empty:
        df_kaynak["Sipariş No"] = df_kaynak["Sipariş No"].astype(str).str.strip()
        makine_ozellikleri = df_kaynak[["Sipariş No", "Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı", "Çelik Çarpanı"]].drop_duplicates("Sipariş No")
        df_m = pd.merge(df_m, makine_ozellikleri, on="Sipariş No", how="left")
    
    # Eksik eşleşmeler (Montajda olup Kaynakta henüz olmayanlar) için varsayılan (1.0) değer ata
    for col in ["Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı", "Çelik Çarpanı"]:
        if col not in df_m.columns: df_m[col] = 1.0
        df_m[col] = df_m[col].fillna(1.0)

    # 3.2. Mesafe Hesaplama ve Mesafe Çarpanı (Turgutlu merkezli)
    # Performans için unique yerlerin mesafesini bir kere hesaplayıp mapliyoruz
    unique_yerler = df_m["Montaj Yeri"].dropna().unique()
    mesafe_sozlugu = {yer: mesafe_hesapla_api(yer) for yer in unique_yerler}
    df_m["Mesafe (km)"] = df_m["Montaj Yeri"].map(mesafe_sozlugu).fillna(10.0)
    
    # Mesafe Çarpanı Mantığı: 0-50km -> 1.0 | 50-200km -> 1.2 | 200-500km -> 1.5 | 500km+ -> 2.0
    def mesafe_carpani_ata(km):
        if km <= 50: return 1.0
        elif km <= 200: return 1.2
        elif km <= 500: return 1.5
        else: return 2.0
    df_m["Mesafe Çarpanı"] = df_m["Mesafe (km)"].apply(mesafe_carpani_ata)

    df_m["Üretim Adedi"] = pd.to_numeric(df_m.get("Üretim Adedi", 1), errors='coerce').fillna(1.0)
    df_m["Net Süre (Gün)"] = (pd.to_datetime(df_m.get("Bitiş"), dayfirst=True, errors='coerce') - pd.to_datetime(df_m.get("Başlangıç"), dayfirst=True, errors='coerce')).dt.days.apply(lambda x: max(x, 1.0) if pd.notna(x) else 1.0)
    df_m["Bekleme Süresi (Gün)"] = 0.0

    # Nihai Montaj İş Yükü (Makinenin ağırlığı ve gidilen yol hesaba katılarak)
    df_m["Ham_İş_Yükü"] = df_m["Zorluk Katsayısı"] * df_m["Normalize_Kapasite"] * df_m["Normalize_Ebat"] * df_m["Mesafe Çarpanı"] * df_m["Üretim Adedi"]
    df_m["Günlük_Hız"] = df_m["Ham_İş_Yükü"] / df_m["Net Süre (Gün)"]
    
    medyan_hiz = df_m["Günlük_Hız"].median()
    df_m["Zaman Verimlilik Çarpanı"] = (df_m["Günlük_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    df_m['Operatörler'] = df_m['Operatörler'].fillna('').astype(str)
    df_m['Kişi Sayısı'] = df_m['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    
    return df_m

# --- GENEL YAPAY ZEKA MODELİ EĞİTİCİSİ ---
@st.cache_resource
def yapay_zeka_egit(df_model, X_cols, net_sure_col="Net Üretim Süresi (Gün)"):
    df_model = df_model.dropna(subset=[net_sure_col, "Bekleme Süresi (Gün)"] + X_cols).copy()
    df_model = df_model[df_model[net_sure_col] > 0]
    if len(df_model) < 5: return None, None, None, None, None
    
    X = df_model[X_cols].values
    y_net = df_model[net_sure_col].values
    y_bek = df_model["Bekleme Süresi (Gün)"].values
    
    X_train, X_test, yn_train, yn_test = train_test_split(X, y_net, test_size=0.25, random_state=42)
    _, _, yb_train, yb_test = train_test_split(X, y_bek, test_size=0.25, random_state=42)
    
    sc = StandardScaler()
    X_train_s = sc.fit_transform(X_train)
    X_test_s = sc.transform(X_test)
    
    rf_net = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42).fit(X_train_s, yn_train)
    rf_bek = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42).fit(X_train_s, yb_train)
    
    metrikler = {
        "Net_MAE": mean_absolute_error(yn_test, rf_net.predict(X_test_s)),
        "Net_RMSE": np.sqrt(mean_squared_error(yn_test, rf_net.predict(X_test_s))),
        "Bekleme_MAE": mean_absolute_error(yb_test, rf_bek.predict(X_test_s)),
        "Bekleme_RMSE": np.sqrt(mean_squared_error(yb_test, rf_bek.predict(X_test_s))),
    }
    return rf_net, rf_bek, sc, rf_net.feature_importances_ * 100, metrikler


# ==========================================
# GÖRÜNÜMLER (UI)
# ==========================================
if secilen_departman == "Kaynak / İmalat Atölyesi":
    try:
        df = veri_isle_kaynak()
        if df.empty: st.error("Veri bulunamadı. Lütfen Google Sheets bağlantısını kontrol edin."); st.stop()
        
        X_Sutunlari = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Normalize_Teknik", "Çelik Çarpanı", "Kişi Sayısı"]
        rf_net, rf_bekleme, sc, onem_yuzdeleri, model_metrikleri = yapay_zeka_egit(df, X_Sutunlari)
        
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Filtreler")
        secilen_tezgah = st.sidebar.selectbox("Tezgah Seçin", ["Tümü"] + sorted(list(df["Tezgah"].dropna().unique())))
        secilen_operator = st.sidebar.selectbox("Operatör Seçin", ["Tümü"] + sorted(list(set(op.strip() for ops in df["Operatörler"].dropna() for op in ops.split(',') if op.strip()))))
        
        df_filtred = df.copy()
        if secilen_tezgah != "Tümü": df_filtred = df_filtred[df_filtred["Tezgah"] == secilen_tezgah]
        if secilen_operator != "Tümü": df_filtred = df_filtred[df_filtred["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]

        tab1, tab2, tab3 = st.tabs(["📊 Ürün Analizi", "👷 Operatör Puanı", "🤖 Yapay Zeka Tahmini"])
        
        with tab1:
            st.subheader("Kaynak Üretim Özeti")
            st.dataframe(df_filtred.groupby(["Model"]).agg({"Zorluk Katsayısı": "mean", "Üretim Adedi": "sum", "Toplam Süre (Gün)": "mean", "Sipariş No": "count"}).reset_index().round(2), use_container_width=True)

        with tab2:
            st.subheader("👷 Kaynak Operatör Puanları")
            if not df_filtred.empty:
                df_op = df_filtred.copy().assign(Operatörler=df_filtred['Operatörler'].str.split(',')).explode('Operatörler')
                df_op['Operatörler'] = df_op['Operatörler'].str.strip()
                df_op = df_op[df_op['Operatörler'] != '']
                df_op['Kişi Başı Puan'] = (df_op['Üretim Adedi'] * df_op['Zorluk Katsayısı'] * df_op['Normalize_Kapasite'] * df_op['Çelik Çarpanı'] * df_op['Normalize_Ebat'] * df_op['Normalize_Teknik'] * df_op['Zaman Verimlilik Çarpanı']) / df_op['Kişi Sayısı']
                st.dataframe(df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum", "Net Üretim Süresi (Gün)": "count"}).reset_index().round(1).sort_values("Kişi Başı Puan", ascending=False), use_container_width=True)

        with tab3:
            st.subheader("🔮 Tahmin Ekranı")
            st.info("Tahmin sekmesi genel yapıda korunmuştur.")
            
    except Exception as e: st.error(f"Hata: {e}")

elif secilen_departman == "Hidrolik Atölyesi":
    try:
        df_hidrolik = veri_isle_hidrolik()
        if df_hidrolik.empty: st.error("Hidrolik verisi çekilemedi (Satır 122'deki GID numarasını kontrol et)."); st.stop()
        
        X_Sutunlari_Hid = ["Normalize_Tank", "Normalize_Motor", "Üretim Adedi", "Kişi Sayısı"]
        rf_net, rf_bekleme, sc, onem_yuzdeleri, model_metrikleri = yapay_zeka_egit(df_hidrolik, X_Sutunlari_Hid)
        
        tab1, tab2 = st.tabs(["📊 Hidrolik Özeti", "👷 Operatör Performansı"])
        with tab1: st.dataframe(df_hidrolik.groupby(["Tezgah"]).agg({"Sipariş No": "count", "Üretim Adedi": "sum", "Net Üretim Süresi (Gün)": "mean"}).reset_index())
        with tab2:
            df_op = df_hidrolik.copy().assign(Operatörler=df_hidrolik['Operatörler'].str.split(',')).explode('Operatörler')
            df_op['Operatörler'] = df_op['Operatörler'].str.strip()
            df_op = df_op[df_op['Operatörler'] != '']
            df_op['Kişi Başı Puan'] = (df_op['Üretim Adedi'] * df_op['Normalize_Tank'] * df_op['Normalize_Motor'] * df_op['Zaman Verimlilik Çarpanı']) / df_op['Kişi Sayısı']
            st.dataframe(df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum"}).reset_index().round(1).sort_values("Kişi Başı Puan", ascending=False))
    except Exception as e: st.error(f"Hata: {e}")

elif secilen_departman == "Montaj Ekibi":
    try:
        df_montaj = veri_isle_montaj()
        if df_montaj.empty: st.error("Montaj verisi çekilemedi (Satır 195'teki GID numarasını kontrol et)."); st.stop()
        
        X_Sutunlari_Mon = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Mesafe Çarpanı", "Kişi Sayısı"]
        rf_net, rf_bekleme, sc, onem_yuzdeleri, model_metrikleri = yapay_zeka_egit(df_montaj, X_Sutunlari_Mon, net_sure_col="Net Süre (Gün)")
        
        tab1, tab2, tab3 = st.tabs(["📊 Montaj Özeti", "👷 Montaj Ekibi Performansı", "🤖 Yapay Zeka Tahmini"])
        
        with tab1:
            st.subheader("Montaj Seferleri ve Makine Eşleşmeleri")
            st.markdown("Sipariş No eşleşmesi sayesinde makinenin teknik detayları üretimden (kaynaktan) otomatik çekilip bu tabloya entegre edilmiştir.")
            gosterim_df = df_montaj[["Sipariş No", "Model", "Montaj Yeri", "Mesafe (km)", "Mesafe Çarpanı", "Ham_İş_Yükü", "Net Süre (Gün)"]]
            st.dataframe(gosterim_df.round(2), use_container_width=True)

        with tab2:
            st.subheader("👷 Montajcı Puanları (Gecikmelerden Arındırılmış)")
            df_op = df_montaj.copy().assign(Operatörler=df_montaj['Operatörler'].str.split(',')).explode('Operatörler')
            df_op['Operatörler'] = df_op['Operatörler'].str.strip()
            df_op = df_op[df_op['Operatörler'] != '']
            
            # Puanlama: (Temel Zorluk * Kapasite * Ebat * MESAFE ÇARPANI) / Kişi Sayısı
            df_op['Kişi Başı Puan'] = (df_op['Ham_İş_Yükü'] * df_op['Zaman Verimlilik Çarpanı']) / df_op['Kişi Sayısı']
            op_ozet = df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum", "Sipariş No": "count"}).reset_index().round(1)
            op_ozet.rename(columns={"Sipariş No": "Gidilen Montaj"}, inplace=True)
            st.dataframe(op_ozet.sort_values(by="Kişi Başı Puan", ascending=False), use_container_width=True)

        with tab3:
            st.subheader("🔮 Montaj Süresi Tahmini")
            if rf_net is None: st.warning("Bu departmanda modeli eğitmek için en az 5 montaj kaydı gerekli.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    input_model = st.selectbox("Model Seç", sorted(df_montaj["Model"].unique()))
                    input_hedef = st.text_input("Gidilecek Şehir/İlçe (Örn: Çorlu, Tekirdağ)")
                with col2:
                    input_kisi = st.number_input("Montaj Ekibi Kişi Sayısı", min_value=1, value=2)

                if st.button("🚀 Montaj Süresini Tahmin Et"):
                    mesafe = mesafe_hesapla_api(input_hedef)
                    m_carpan = 1.0 if mesafe <= 50 else (1.2 if mesafe <= 200 else (1.5 if mesafe <= 500 else 2.0))
                    
                    # Modelden ortalama teknik değerleri alıyoruz
                    model_ortalamalari = df_montaj[df_montaj["Model"] == input_model][["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat"]].mean()
                    z_kat = model_ortalamalari["Zorluk Katsayısı"] if pd.notna(model_ortalamalari["Zorluk Katsayısı"]) else 1.5
                    n_kap = model_ortalamalari["Normalize_Kapasite"] if pd.notna(model_ortalamalari["Normalize_Kapasite"]) else 1.2
                    n_ebt = model_ortalamalari["Normalize_Ebat"] if pd.notna(model_ortalamalari["Normalize_Ebat"]) else 1.2

                    ham_veri = np.array([[z_kat, n_kap, n_ebt, m_carpan, input_kisi]])
                    tahmini_net_gun = max(rf_net.predict(sc.transform(ham_veri))[0], 0.5)
                    st.success(f"### 📍 {input_hedef} ({mesafe:.1f} km) için Tahmini Süre: **{tahmini_net_gun:.1f} Gün**")

    except Exception as e: st.error(f"Hata: {e}")
