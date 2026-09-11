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

    if st.session_state.get("sifre_dogru", False): return True
    st.markdown("### 🔒 Zafer Lift - Güvenli Giriş")
    st.text_input("Panele erişmek için şifrenizi girip Enter'a basın:", type="password", on_change=sifre_girildi, key="sifre_kutusu")
    if "sifre_dogru" in st.session_state and not st.session_state["sifre_dogru"]:
        st.error("❌ Hatalı Şifre! Lütfen tekrar deneyin.")
    return False

if not sifre_kontrol(): st.stop()

st.title("🚀 Zafer Lift Makine - Genel Üretim ve Operatör Performans Panosu")
st.markdown("Tüm atölye ve montaj verileri Google Sheets üzerinden canlı olarak senkronize edilmektedir.")

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

# ==========================================
# 1. KAYNAK ATÖLYESİ VERİ İŞLEME
# ==========================================
@st.cache_data(ttl=5)
def veri_isle_kaynak():
    sheet_url = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=0"
    try: df = pd.read_csv(sheet_url)
    except: return pd.DataFrame()
    if df.empty: return df
    
    def urun_normalize(deger):
        if pd.isna(deger): return ""
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
        return float(match.group()) / 1000.0 if match and (float(match.group()) > 50 or "kg" in s) else (float(match.group()) if match else 1.0)

    def metrekare_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '': return 1.0
        s = str(deger).lower().replace(' ', '').replace(',', '.')
        parcalar = re.split(r'[\*x]', s)
        if len(parcalar) == 2:
            try: return (float(re.search(r'[\d\.]+', parcalar[0]).group()) * float(re.search(r'[\d\.]+', parcalar[1]).group())) / 1_000_000.0
            except: pass
        match = re.search(r'[\d\.]+', s)
        return float(match.group()) / 1_000_000.0 if match and float(match.group()) > 100 else (float(match.group()) if match else 1.0)
        
    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Model", "Çelik Durumu (1/0)", "Kapasite", "Platform Ebat mm", "Platform Ebat (m2)", "Teknik Puan", "Süre(Saat)", "Tezgah", "Operatörler", "Üretim Adedi", "Tel Fonk", "Tabla Kapısı", "Kilitleme"]
    for col in hedef_sutunlar:
        if col not in df.columns: df[col] = 0.0 if "Durumu" in col or col in ["Tabla Kapısı", "Kilitleme", "Üretim Adedi", "Süre(Saat)"] else ""
    df = df[hedef_sutunlar]

    df["Sipariş No"] = df["Sipariş No"].fillna("BELİRSİZ").astype(str)
    df["Model"] = df["Model"].apply(urun_normalize)
    df["Tezgah"] = df["Tezgah"].fillna("Makaslı-1")
    df["Departman"] = "Kaynak"
    
    df["Üretim Adedi"] = pd.to_numeric(df["Üretim Adedi"], errors='coerce').fillna(1.0)
    df["Ham_Zorluk"] = df["Model"].apply(dinamik_zorluk)
    
    celik_val = pd.to_numeric(df["Çelik Durumu (1/0)"], errors='coerce').fillna(0.0)
    df["Çelik Çarpanı"] = celik_val + 1.0
    
    val_tabla = pd.to_numeric(df["Tabla Kapısı"], errors='coerce').fillna(0.0)
    df["Tabla_Carpani"] = np.where(val_tabla > 0, 1.1, 1.0)

    val_kilit = pd.to_numeric(df["Kilitleme"], errors='coerce').fillna(0.0)
    df["Kilitleme_Carpani"] = np.where(val_kilit > 0, 1.2, 1.0)

    df["Kapasite_G"] = df["Kapasite"].apply(kapasite_ayikla).replace(0, 1.0)
    if "Platform Ebat (m2)" not in df.columns and "Platform Ebat mm" in df.columns: df["Platform Ebat (m2)"] = df["Platform Ebat mm"]
    df["Ebat_G"] = df["Platform Ebat (m2)"].apply(metrekare_ayikla).replace(0, 1.0)
    df["Teknik Puan"] = pd.to_numeric(df["Teknik Puan"], errors='coerce').fillna(1.0)
    
    df["Net Süre"] = pd.to_numeric(df["Süre(Saat)"], errors='coerce').fillna(1.0).apply(lambda x: max(x, 0.1))

    min_kap, max_kap = df["Kapasite_G"].min(), df["Kapasite_G"].max()
    df["Normalize_Kapasite"] = 1.0 if max_kap == min_kap else 1.0 + ((df["Kapasite_G"] - min_kap) / (max_kap - min_kap)) * (MAKSIMUM_CARPAN_KAPASITE - 1.0)
    makasli_mask = df["Model"].apply(urun_makasli_mi)
    min_m2, max_m2 = (df.loc[makasli_mask, "Ebat_G"].min(), df.loc[makasli_mask, "Ebat_G"].max()) if makasli_mask.any() else (1.0, 1.0)
    df["Normalize_Ebat"] = df.apply(lambda row: 1.0 + ((row["Ebat_G"] - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0) if urun_makasli_mi(row["Model"]) and max_m2 > min_m2 else 1.0, axis=1)
    df["Normalize_Teknik"] = 1.0 + ((df["Teknik Puan"] - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
    
    min_hz, max_hz = df["Ham_Zorluk"].min(), df["Ham_Zorluk"].max()
    df["Zorluk Katsayısı"] = 1.0 if max_hz == min_hz else 1.0 + ((df["Ham_Zorluk"] - min_hz) / (max_hz - min_hz)) * 9.0

    df["Ham_İş_Yükü"] = df['Zorluk Katsayısı'] * df['Normalize_Kapasite'] * df['Çelik Çarpanı'] * df['Normalize_Ebat'] * df['Normalize_Teknik'] * df['Tabla_Carpani'] * df['Kilitleme_Carpani'] * df['Üretim Adedi']
    df["Saatlik_Hız"] = df["Ham_İş_Yükü"] / df["Net Süre"]
    medyan_hiz = df["Saatlik_Hız"].median()
    df["Zaman Verimlilik Çarpanı"] = (df["Saatlik_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    
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
    except: return pd.DataFrame() 
    if df.empty: return df

    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Süre(Saat)", "Tezgah", "Operatörler", "Üretim Adedi", "Yağ Tankı(lt)", "Motor(kW)"]
    for col in hedef_sutunlar:
        if col not in df.columns: df[col] = 1.0 if col in ["Üretim Adedi", "Süre(Saat)"] else ""
    df = df[hedef_sutunlar]

    df["Sipariş No"] = df["Sipariş No"].fillna("BELİRSİZ").astype(str).str.strip()
    df["Tezgah"] = df["Tezgah"].fillna("Hidrolik")
    df["Departman"] = "Hidrolik"
    df["Üretim Adedi"] = pd.to_numeric(df["Üretim Adedi"], errors='coerce').fillna(1.0)

    df_kaynak = veri_isle_kaynak()
    if not df_kaynak.empty:
        df_kaynak["Sipariş No"] = df_kaynak["Sipariş No"].astype(str).str.strip()
        makine_ozellikleri = df_kaynak[["Sipariş No", "Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı"]].drop_duplicates("Sipariş No")
        df = pd.merge(df, makine_ozellikleri, on="Sipariş No", how="left")
    
    for col in ["Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı"]:
        if col not in df.columns: df[col] = 1.0
        df[col] = df[col].fillna(1.0)

    def parse_sayisal(val):
        if pd.isna(val) or str(val).strip() == '': return 1.0
        nums = re.findall(r"[\d\.]+", str(val).replace(',', '.'))
        valid = [float(n) for n in nums if n.count('.') <= 1]
        return max(valid) if valid else 1.0

    df["Tank_Val"] = df["Yağ Tankı(lt)"].apply(parse_sayisal)
    df["Motor_Val"] = df["Motor(kW)"].apply(parse_sayisal)
    df["Net Süre"] = pd.to_numeric(df["Süre(Saat)"], errors='coerce').fillna(1.0).apply(lambda x: max(x, 0.1))

    min_m, max_m = df["Motor_Val"].min(), df["Motor_Val"].max()
    df["Normalize_Motor"] = 1.0 if max_m == min_m else 1.0 + ((df["Motor_Val"] - min_m) / (max_m - min_m)) * (1.5 - 1.0)
    min_t, max_t = df["Tank_Val"].min(), df["Tank_Val"].max()
    df["Normalize_Tank"] = 1.0 if max_t == min_t else 1.0 + ((df["Tank_Val"] - min_t) / (max_t - min_t)) * (3.0 - 1.0)

    df["Ham_İş_Yükü"] = df["Zorluk Katsayısı"] * df["Normalize_Kapasite"] * df["Normalize_Ebat"] * df["Normalize_Tank"] * df["Normalize_Motor"] * df["Üretim Adedi"]
    df["Saatlik_Hız"] = df["Ham_İş_Yükü"] / df["Net Süre"]
    medyan_hiz = df["Saatlik_Hız"].median()
    df["Zaman Verimlilik Çarpanı"] = (df["Saatlik_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    df['Operatörler'] = df['Operatörler'].fillna('').astype(str)
    df['Kişi Sayısı'] = df['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    return df

# ==========================================
# 3. MONTAJ EKİBİ VERİ İŞLEME
# ==========================================
@st.cache_data(ttl=86400)
def mesafe_hesapla_api(hedef_sehir):
    if pd.isna(hedef_sehir) or str(hedef_sehir).strip() == "": return 10.0
    try:
        geolocator = Nominatim(user_agent="zafer_lift_app")
        merkez = geolocator.geocode("Turgutlu, Manisa, Turkey")
        hedef = geolocator.geocode(f"{hedef_sehir}, Turkey")
        if merkez and hedef: return geodesic((merkez.latitude, merkez.longitude), (hedef.latitude, hedef.longitude)).km
    except: pass
    return 50.0 

@st.cache_data(ttl=5)
def veri_isle_montaj():
    sheet_url_montaj = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=857495736"
    try: df_m = pd.read_csv(sheet_url_montaj)
    except: return pd.DataFrame()
    if df_m.empty: return df_m

    df_m.columns = df_m.columns.str.strip()
    hedef_sutunlar_m = ["Sipariş No", "Süre(Saat)", "Tezgah", "Operatörler", "Üretim Adedi", "Montaj Yeri", "Model", "Ortam", "Montaj durumu"]
    for col in hedef_sutunlar_m:
        if col not in df_m.columns: df_m[col] = 1.0 if col in ["Üretim Adedi", "Süre(Saat)"] else ""
    df_m = df_m[hedef_sutunlar_m]

    df_m["Sipariş No"] = df_m["Sipariş No"].fillna("BELİRSİZ").astype(str).str.strip()
    df_m["Tezgah"] = df_m["Tezgah"].fillna("Montaj Ekibi")
    df_m["Departman"] = "Montaj"
    df_m["Üretim Adedi"] = pd.to_numeric(df_m["Üretim Adedi"], errors='coerce').fillna(1.0)
        
    df_kaynak = veri_isle_kaynak()
    if not df_kaynak.empty:
        df_kaynak["Sipariş No"] = df_kaynak["Sipariş No"].astype(str).str.strip()
        makine_ozellikleri = df_kaynak[["Sipariş No", "Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı", "Çelik Çarpanı", "Tabla_Carpani", "Kilitleme_Carpani"]].drop_duplicates("Sipariş No")
        df_m = pd.merge(df_m, makine_ozellikleri, on="Sipariş No", how="left")
    
    for col in ["Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı", "Çelik Çarpanı", "Tabla_Carpani", "Kilitleme_Carpani"]:
        if col not in df_m.columns: df_m[col] = 1.0
        df_m[col] = df_m[col].fillna(1.0)

    unique_yerler = df_m["Montaj Yeri"].dropna().unique()
    mesafe_sozlugu = {yer: mesafe_hesapla_api(yer) for yer in unique_yerler}
    df_m["Mesafe (km)"] = df_m["Montaj Yeri"].map(mesafe_sozlugu).fillna(10.0)
    
    min_km, max_km = df_m["Mesafe (km)"].min(), df_m["Mesafe (km)"].max()
    df_m["Normalize_Mesafe"] = 1.0 if max_km == min_km else 1.0 + ((df_m["Mesafe (km)"] - min_km) / (max_km - min_km)) * 1.5

    def ortam_montaj_carpani(row):
        ortam = str(row.get("Ortam", "")).strip().lower()
        durum = str(row.get("Montaj durumu", "")).strip().lower()
        if "1" in ortam or "iç" in ortam or "ic" in ortam:
            if "vinç" in durum or "vinc" in durum: return 2.0
            elif "manuel" in durum or "el" in durum: return 4.0
            return 2.0 
        return 1.0 

    df_m["Ortam_Montaj_Çarpanı"] = df_m.apply(ortam_montaj_carpani, axis=1)
    df_m["Net Süre"] = pd.to_numeric(df_m["Süre(Saat)"], errors='coerce').fillna(1.0).apply(lambda x: max(x, 0.1))

    df_m["Ham_İş_Yükü"] = df_m["Zorluk Katsayısı"] * df_m["Normalize_Kapasite"] * df_m["Normalize_Ebat"] * df_m["Tabla_Carpani"] * df_m["Kilitleme_Carpani"] * df_m["Normalize_Mesafe"] * df_m["Ortam_Montaj_Çarpanı"] * df_m["Üretim Adedi"]
    df_m["Saatlik_Hız"] = df_m["Ham_İş_Yükü"] / df_m["Net Süre"]
    medyan_hiz = df_m["Saatlik_Hız"].median()
    df_m["Zaman Verimlilik Çarpanı"] = (df_m["Saatlik_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    df_m['Operatörler'] = df_m['Operatörler'].fillna('').astype(str)
    df_m['Kişi Sayısı'] = df_m['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    return df_m

# ==========================================
# 4. ELEKTRİK ATÖLYESİ VERİ İŞLEME
# ==========================================
@st.cache_data(ttl=5)
def veri_isle_elektrik():
    sheet_url_elektrik = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv&gid=1648152517"
    try: df_e = pd.read_csv(sheet_url_elektrik)
    except: return pd.DataFrame()
    if df_e.empty: return df_e

    df_e.columns = df_e.columns.str.strip()
    hedef_sutunlar_e = ["Sipariş No", "Süre(Saat)", "Tezgah", "Operatörler", "Üretim Adedi", "Model", "Durak Sayısı", "Kilitleme", "PLC", "PLC Model", "Sıfırlama", "Tabla Kapısı", "Yavaşlama", "Buton Tipi", "İkaz Lambaları"]
    for col in hedef_sutunlar_e:
        if col not in df_e.columns: df_e[col] = 1.0 if col in ["Üretim Adedi", "Durak Sayısı", "Süre(Saat)"] else (0.0 if col in ["Kilitleme", "PLC", "Sıfırlama", "Tabla Kapısı", "Yavaşlama", "Buton Tipi", "İkaz Lambaları"] else "")
    df_e = df_e[hedef_sutunlar_e]

    df_e["Sipariş No"] = df_e["Sipariş No"].fillna("BELİRSİZ").astype(str).str.strip()
    df_e["Tezgah"] = df_e["Tezgah"].fillna("Elektrik")
    df_e["Departman"] = "Elektrik"
    df_e["Üretim Adedi"] = pd.to_numeric(df_e["Üretim Adedi"], errors='coerce').fillna(1.0)

    df_kaynak = veri_isle_kaynak()
    if not df_kaynak.empty:
        df_kaynak["Sipariş No"] = df_kaynak["Sipariş No"].astype(str).str.strip()
        makine_ozellikleri = df_kaynak[["Sipariş No", "Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı"]].drop_duplicates("Sipariş No")
        df_e = pd.merge(df_e, makine_ozellikleri, on="Sipariş No", how="left")
    
    for col in ["Normalize_Kapasite", "Normalize_Ebat", "Zorluk Katsayısı"]:
        if col not in df_e.columns: df_e[col] = 1.0
        df_e[col] = df_e[col].fillna(1.0)

    durak_vals = pd.to_numeric(df_e["Durak Sayısı"], errors='coerce').fillna(1.0)
    min_d, max_d = durak_vals.min(), durak_vals.max()
    df_e["Normalize_Durak"] = 1.0 if max_d == min_d else 1.0 + ((durak_vals - min_d) / (max_d - min_d)) * 0.5

    parametre_listesi = ["Kilitleme", "Sıfırlama", "Tabla Kapısı", "Yavaşlama", "Buton Tipi", "İkaz Lambaları"]
    for p in parametre_listesi:
        val = pd.to_numeric(df_e[p], errors='coerce').fillna(0.0)
        df_e[f"{p}_Carpani"] = np.where(val > 0, 1.2, 1.0)

    plc_val = pd.to_numeric(df_e["PLC"], errors='coerce').fillna(0.0)
    df_e["PLC_Carpani"] = np.where(plc_val > 0, 1.2, 1.0)

    def plc_model_carpani(row):
        p_val = pd.to_numeric(row.get("PLC", 0.0), errors='coerce')
        if pd.isna(p_val) or p_val == 0: return 1.0
        model = str(row.get("PLC Model", "")).strip().lower()
        if any(m in model for m in ["gemo", "delta", "omron", "schneider", "siemens"]):
            return 1.1
        return 1.1

    df_e["PLC_Model_Carpani"] = df_e.apply(plc_model_carpani, axis=1)

    df_e["Net Süre"] = pd.to_numeric(df_e["Süre(Saat)"], errors='coerce').fillna(1.0).apply(lambda x: max(x, 0.1))

    df_e["Ham_İş_Yükü"] = (
        df_e["Zorluk Katsayısı"] * df_e["Normalize_Kapasite"] * df_e["Normalize_Ebat"] * 
        df_e["Normalize_Durak"] * df_e["Kilitleme_Carpani"] * df_e["Sıfırlama_Carpani"] * 
        df_e["Tabla Kapısı_Carpani"] * df_e["Yavaşlama_Carpani"] * df_e["Buton Tipi_Carpani"] * 
        df_e["İkaz Lambaları_Carpani"] * df_e["PLC_Carpani"] * df_e["PLC_Model_Carpani"] * df_e["Üretim Adedi"]
    )
    
    df_e["Saatlik_Hız"] = df_e["Ham_İş_Yükü"] / df_e["Net Süre"]
    medyan_hiz = df_e["Saatlik_Hız"].median()
    df_e["Zaman Verimlilik Çarpanı"] = (df_e["Saatlik_Hız"] / (medyan_hiz if pd.notna(medyan_hiz) and medyan_hiz != 0 else 1.0)).clip(lower=0.85, upper=1.15)
    df_e['Operatörler'] = df_e['Operatörler'].fillna('').astype(str)
    df_e['Kişi Sayısı'] = df_e['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1).replace(0, 1)
    return df_e

# --- YZ MODELİ (SAAT BAZLI) ---
@st.cache_resource
def yapay_zeka_egit(df_model, X_cols):
    df_m = df_model.dropna(subset=["Net Süre"] + X_cols).copy()
    df_m = df_m[df_m["Net Süre"] > 0]
    if len(df_m) < 5: return None, None, None, None, None
    X = df_m[X_cols].values
    y_net = df_m["Net Süre"].values
    X_train, X_test, yn_train, yn_test = train_test_split(X, y_net, test_size=0.25, random_state=42)
    sc = StandardScaler()
    X_train_s = sc.fit_transform(X_train)
    rf_net = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42).fit(X_train_s, yn_train)
    metrikler = {"Net_MAE": mean_absolute_error(yn_test, rf_net.predict(sc.transform(X_test)))}
    return rf_net, None, sc, rf_net.feature_importances_ * 100, metrikler


# ==========================================
# ANA UYGULAMA VE VERİ BİRLEŞTİRME
# ==========================================
df_k = veri_isle_kaynak()
df_h = veri_isle_hidrolik()
df_m = veri_isle_montaj()
df_e = veri_isle_elektrik()

tezgahlar_k = list(df_k["Tezgah"].dropna().unique()) if not df_k.empty else []
tezgahlar_h = list(df_h["Tezgah"].dropna().unique()) if not df_h.empty else []
tezgahlar_m = list(df_m["Tezgah"].dropna().unique()) if not df_m.empty else []
tezgahlar_e = list(df_e["Tezgah"].dropna().unique()) if not df_e.empty else []
tum_tezgahlar = sorted(tezgahlar_k + tezgahlar_h + tezgahlar_m + tezgahlar_e)

def get_op_points(df):
    if df.empty: return pd.DataFrame()
    d = df.copy()
    d['Operatörler'] = d['Operatörler'].str.split(',')
    d = d.explode('Operatörler')
    d['Operatörler'] = d['Operatörler'].str.strip()
    d = d[d['Operatörler'] != '']
    d['Kişi Başı Puan'] = (d['Ham_İş_Yükü'] * d['Zaman Verimlilik Çarpanı']) / d['Kişi Sayısı']
    return d[['Operatörler', 'Kişi Başı Puan', 'Tezgah', 'Departman', 'Sipariş No']]

op_k = get_op_points(df_k)
op_h = get_op_points(df_h)
op_m = get_op_points(df_m)
op_e = get_op_points(df_e)
df_op_all = pd.concat([op_k, op_h, op_m, op_e], ignore_index=True)

tum_operatorler = sorted(list(df_op_all["Operatörler"].unique())) if not df_op_all.empty else []

# --- SOL MENÜ (FİLTRELER) ---
st.sidebar.header("🔍 Fabrika Filtreleri")
st.sidebar.info("💡 'Tümü' seçiliyken ürün analizinde sadece Kaynak Atölyesi gösterilir. Özel birimleri incelemek için listeden seçin.")
secilen_tezgah = st.sidebar.selectbox("İstasyon / Tezgah Seçin", ["Tümü"] + tum_tezgahlar)
secilen_operator = st.sidebar.selectbox("Operatör Seçin", ["Tümü"] + tum_operatorler)

# --- SEKME DÜZENİ ---
tab1, tab2, tab3 = st.tabs(["📊 Ürün Analizi", "👷 Ortak Operatör Puanı", "🤖 Yapay Zeka Tahmini"])

with tab1:
    if secilen_tezgah == "Tümü" or secilen_tezgah in tezgahlar_k:
        st.subheader("🛠️ Kaynak & İmalat Üretim Özeti")
        if not df_k.empty:
            df_k_filt = df_k.copy()
            if secilen_tezgah != "Tümü": df_k_filt = df_k_filt[df_k_filt["Tezgah"] == secilen_tezgah]
            if secilen_operator != "Tümü": df_k_filt = df_k_filt[df_k_filt["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]
            st.dataframe(df_k_filt.groupby(["Model"]).agg({"Zorluk Katsayısı": "mean", "Üretim Adedi": "sum", "Net Süre": "mean", "Sipariş No": "count"}).reset_index().round(2), use_container_width=True)
    
    elif secilen_tezgah in tezgahlar_h:
        st.subheader("💧 Hidrolik Atölyesi Özeti")
        if not df_h.empty:
            df_h_filt = df_h[df_h["Tezgah"] == secilen_tezgah]
            if secilen_operator != "Tümü": df_h_filt = df_h_filt[df_h_filt["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]
            gosterim_h = df_h_filt[["Sipariş No", "Üretim Adedi", "Yağ Tankı(lt)", "Motor(kW)", "Ham_İş_Yükü", "Net Süre"]]
            st.dataframe(gosterim_h.round(2), use_container_width=True)

    elif secilen_tezgah in tezgahlar_m:
        st.subheader("🚚 Montaj Seferleri ve Özeti")
        if not df_m.empty:
            df_m_filt = df_m[df_m["Tezgah"] == secilen_tezgah]
            if secilen_operator != "Tümü": df_m_filt = df_m_filt[df_m_filt["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]
            gosterim_df = df_m_filt[["Sipariş No", "Model", "Montaj Yeri", "Mesafe (km)", "Normalize_Mesafe", "Ortam_Montaj_Çarpanı", "Ham_İş_Yükü", "Net Süre"]]
            st.dataframe(gosterim_df.round(2), use_container_width=True)

    elif secilen_tezgah in tezgahlar_e:
        st.subheader("⚡ Elektrik Atölyesi Özeti")
        if not df_e.empty:
            df_e_filt = df_e[df_e["Tezgah"] == secilen_tezgah]
            if secilen_operator != "Tümü": df_e_filt = df_e_filt[df_e_filt["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]
            gosterim_e = df_e_filt[["Sipariş No", "Model", "Durak Sayısı", "PLC", "PLC Model", "Ham_İş_Yükü", "Net Süre"]]
            st.dataframe(gosterim_e.round(2), use_container_width=True)

with tab2:
    st.subheader("🏆 Fabrika Geneli Operatör Performans Sıralaması")
    st.markdown("*(Tüm atölye personelleri ortak havuzda saat bazlı puanlanmaktadır.)*")
    if not df_op_all.empty:
        op_gosterim = df_op_all.copy()
        if secilen_tezgah != "Tümü": op_gosterim = op_gosterim[op_gosterim["Tezgah"] == secilen_tezgah]
        if secilen_operator != "Tümü": op_gosterim = op_gosterim[op_gosterim["Operatörler"] == secilen_operator]
        
        final_op_tablosu = op_gosterim.groupby("Operatörler").agg(
            {"Kişi Başı Puan": "sum", "Sipariş No": "count", "Departman": lambda x: ", ".join(x.unique())}
        ).reset_index().round(1).sort_values("Kişi Başı Puan", ascending=False)
        final_op_tablosu.rename(columns={"Sipariş No": "Tamamlanan İş"}, inplace=True)
        st.dataframe(final_op_tablosu, use_container_width=True)
    else:
        st.info("Gösterilecek operatör verisi bulunamadı.")

with tab3:
    st.subheader("🔮 Yapay Zeka Süre (Saat) Tahmini")
    yz_departman = st.radio("Hangi atölye için tahmin yapmak istiyorsunuz?", ["Kaynak İmalatı", "Hidrolik Ünitesi", "Montaj Seferi", "Elektrik Atölyesi"], horizontal=True)
    
    if yz_departman == "Kaynak İmalatı" and not df_k.empty:
        X_k = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Normalize_Teknik", "Çelik Çarpanı", "Tabla_Carpani", "Kilitleme_Carpani", "Kişi Sayısı"]
        rf_net, _, sc, _, metrik_k = yapay_zeka_egit(df_k, X_k)
        if rf_net:
            col1, col2 = st.columns(2)
            with col1:
                in_k_urun = st.selectbox("Model", sorted(df_k["Model"].unique()))
                in_k_kapasite = st.number_input("Kapasite (Ton)", value=1.0)
                in_k_m2 = st.number_input("Platform Ebatı (m2)", value=5.0)
                in_k_tabla = st.selectbox("Tabla Kapısı", [0, 1])
            with col2:
                in_k_kisi = st.number_input("Ekip Sayısı", min_value=1, value=1)
                in_k_teknik = st.slider("Teknik Zorluk", 1.0, 10.0, 1.0)
                in_k_celik = st.selectbox("Çelik Durumu", [0, 1])
                in_k_kilit = st.selectbox("Kilitleme", [0, 1])
            if st.button("🚀 Tahmin Et (Kaynak)"):
                t_carp = 1.1 if in_k_tabla == 1 else 1.0
                k_carp = 1.2 if in_k_kilit == 1 else 1.0
                ham_veri = np.array([[2.5, 1.2, 1.1, 1.0 + (in_k_teknik/10), in_k_celik+1.0, t_carp, k_carp, in_k_kisi]]) 
                st.success(f"🎯 Tahmini Süre: **{max(rf_net.predict(sc.transform(ham_veri))[0], 0.5):.1f} Saat**")
        else: st.warning("Yeterli veri yok.")

    elif yz_departman == "Hidrolik Ünitesi" and not df_h.empty:
        X_h = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Normalize_Tank", "Normalize_Motor", "Üretim Adedi", "Kişi Sayısı"]
        rf_net, _, sc, _, metrik_h = yapay_zeka_egit(df_h, X_h)
        if rf_net:
            col1, col2 = st.columns(2)
            with col1:
                in_h_tank = st.number_input("Yağ Tankı (Litre)", min_value=1.0, value=200.0)
                in_h_motor = st.number_input("Motor Gücü (kW)", min_value=0.1, value=5.5)
            with col2:
                in_h_adet = st.number_input("Üretim Adedi", min_value=1, value=1)
                in_h_kisi = st.number_input("Ekipteki Operatör Sayısı", min_value=1, value=2)
            if st.button("🚀 Tahmin Et (Hidrolik)"):
                norm_t = 1.0 + ((in_h_tank - df_h["Tank_Val"].min()) / (df_h["Tank_Val"].max() - df_h["Tank_Val"].min())) * 2.0 if df_h["Tank_Val"].max() > df_h["Tank_Val"].min() else 1.0
                norm_m = 1.0 + ((in_h_motor - df_h["Motor_Val"].min()) / (df_h["Motor_Val"].max() - df_h["Motor_Val"].min())) * 0.5 if df_h["Motor_Val"].max() > df_h["Motor_Val"].min() else 1.0
                st.success(f"🎯 Tahmini Süre: **{max(rf_net.predict(sc.transform(np.array([[1.5, 1.2, 1.2, norm_t, norm_m, in_h_adet, in_h_kisi]])))[0], 0.5):.1f} Saat**")
        else: st.warning("Yeterli veri yok.")

    elif yz_departman == "Montaj Seferi" and not df_m.empty:
        X_m = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Tabla_Carpani", "Kilitleme_Carpani", "Normalize_Mesafe", "Ortam_Montaj_Çarpanı", "Kişi Sayısı"]
        rf_net, _, sc, _, metrik_m = yapay_zeka_egit(df_m, X_m)
        if rf_net:
            col1, col2 = st.columns(2)
            with col1:
                in_m_hedef = st.text_input("Gidilecek Şehir/İlçe (Örn: Çorlu, Tekirdağ)")
                in_m_ortam = st.selectbox("Montaj Ortamı", ["Dış (0)", "İç (1)"])
            with col2:
                in_m_durum = st.selectbox("Montaj Durumu", ["Vinç", "Manuel"])
                in_m_kisi = st.number_input("Montaj Ekibi Kişi Sayısı", min_value=1, value=2)
            if st.button("🚀 Tahmin Et (Montaj)"):
                mesafe = mesafe_hesapla_api(in_m_hedef)
                o_carp = 1.0 if "Dış" in in_m_ortam else (2.0 if "Vinç" in in_m_durum else 4.0)
                st.success(f"📍 {in_m_hedef} ({mesafe:.1f} km) için Tahmini Süre: **{max(rf_net.predict(sc.transform(np.array([[1.5, 1.2, 1.2, 1.0, 1.0, 1.2, o_carp, in_m_kisi]])))[0], 0.5):.1f} Saat**")
        else: st.warning("Yeterli veri yok.")

    elif yz_departman == "Elektrik Atölyesi" and not df_e.empty:
        X_e = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Normalize_Durak", "Kilitleme_Carpani", "Sıfırlama_Carpani", "Tabla Kapısı_Carpani", "Yavaşlama_Carpani", "Buton Tipi_Carpani", "İkaz Lambaları_Carpani", "PLC_Carpani", "PLC_Model_Carpani", "Kişi Sayısı"]
        rf_net, _, sc, _, metrik_e = yapay_zeka_egit(df_e, X_e)
        if rf_net:
            col1, col2 = st.columns(2)
            with col1:
                in_e_durak = st.number_input("Durak Sayısı", min_value=1, value=3)
                in_e_plc = st.selectbox("PLC Var mı?", [0, 1])
                in_e_model = st.selectbox("PLC Model", ["Gemo", "Delta", "Omron", "Schneider", "Siemens"])
            with col2:
                in_e_kisi = st.number_input("Elektrik Ekibi Kişi Sayısı", min_value=1, value=2)
            if st.button("🚀 Tahmin Et (Elektrik)"):
                p_carp = 1.2 if in_e_plc == 1 else 1.0
                m_carp = 1.1 if in_e_plc == 1 else 1.0
                ham_e = np.array([[1.5, 1.2, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, p_carp, m_carp, in_e_kisi]])
                st.success(f"🎯 Tahmini Süre: **{max(rf_net.predict(sc.transform(ham_e))[0], 0.5):.1f} Saat**")
        else: st.warning("Yeterli veri yok.")
