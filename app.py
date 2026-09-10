import pandas as pd
import numpy as np
import re
import streamlit as st
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
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

st.title("🚀 Zafer Lift Makine - Üretim Kapasitesi ve Operatör Performans Panosu")
st.markdown("Bu pano, Google Sheets bulut altyapısıyla canlı olarak senkronize edilmiştir.")

# --- ZORLUK HARİTASI (GLOBAL) ---
ZORLUK_HARITASI = {
    "EYP1Ç": 1.0, "HYM2": 1.0, "HYM1": 1.0, "HYM2EAP": 1.0, "HR": 1.0,
    "EYP2": 1.0, "EYP3": 1.0, "EYP1": 1.0, "EAP2": 1.0, "EYP1U": 1.0,
    "EYP4": 1.0, "EYP1S12": 1.0, "EYP1S11": 1.0, "EAP1": 1.0, "EYP1T": 1.0,
    "EEP3": 1.0, "EYP1H": 1.0, "EYP1A": 1.0, "EEP2": 1.0, "EEP1": 1.0,
    "PYM157ÖZEL": 1.0, "HYM2T": 1.0, "HYM4": 1.0, "EYP2H": 1.0,
    "DÜZRAMPA": 1.0, "MENTEŞELİRAMPA": 2.0, "MENLİFT": 2.5, 
    "1MAKASLI": 3.0, "2MAKASLI": 4.5, "3MAKASLI": 6.0,
    "1KOLONLU": 3.5, "2KOLONLU": 5.0, "4KOLONLU": 8.0,
    "ENGELLİRAMPASI": 1.0
}

MAKSIMUM_CARPAN_KAPASITE = 2.0   
MAKSIMUM_CARPAN_M2 = 1.3       
MAKSIMUM_CARPAN_TEKNIK = 1.5   

# --- KATEGORİ AYIRICI FONKSİYON ---
MAKASLI_KODLAR = [
    "EYP1Ç", "EYP2", "EYP3", "EYP1", "EAP2", "EYP1U", 
    "EYP4", "EYP1S12", "EYP1S11", "EAP1", "EYP1T", 
    "EEP3", "EYP1H", "EYP1A", "EEP2", "EEP1", 
    "PYM157ÖZEL", "EYP2H", "HR"
]

def urun_makasli_mi(urun):
    urun_str = str(urun).upper().replace("İ", "I").replace("ı", "I")
    if "MAKASLI" in urun_str: 
        return True
    for kod in MAKASLI_KODLAR:
        if kod in urun_str:
            return True
    return False

# --- KENAR ÇUBUĞU KATEGORİ YÖNETİMİ ---
st.sidebar.header("🏗️ Üretim Kategorisi")
secilen_kategori = st.sidebar.radio(
    "Hangi üretim tipini incelemek istiyorsunuz?",
    ["Tümü (Genel Analiz)", "Makaslı Üretimler (Makaslılar, EYP, EEP vb.)", "Asansör ve Diğerleri (Kolonlu, HYM, Rampa vb.)"]
)

# --- VERİ İŞLEME ---
@st.cache_data(ttl=5)
def veri_isle():
    sheet_url = "https://docs.google.com/spreadsheets/d/1CO4--GtXz5qu5Qm0L3jz91x6xfFzmQ-0aZiplKZMLWI/export?format=csv"
    
    try:
        df = pd.read_csv(sheet_url)
    except:
        df = pd.read_excel("personel_listesi_kapasiteli.xlsx")
    
    def urun_normalize(deger):
        if pd.isna(deger): return deger
        s = str(deger).strip().upper()
        s = s.replace("İ", "I").replace("ı", "I") 
        return re.sub(r'[\s\.\-]+', '', s)

    def dinamik_zorluk(urun):
        if pd.isna(urun): return 1.0
        urun_str = str(urun).upper()
        if urun_str in ZORLUK_HARITASI: return ZORLUK_HARITASI[urun_str]
        if any(kod in urun_str for kod in ["EYP", "HYM", "EEP", "EAP"]): return 2.5
        if "ÖZEL" in urun_str or "OZEL" in urun_str:
            if "MAKASLI" in urun_str: return 6.5
            elif "KOLONLU" in urun_str: return 6.0
            return 3.0
        return 1.5

    def kapasite_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '': return 1.0
        s = str(deger).lower().replace(',', '.')
        match = re.search(r'[\d\.]+', s)
        if match:
            sayi = float(match.group())
            if sayi > 50 or "kg" in s: return sayi / 1000.0
            return sayi
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
            if val > 100: return val / 1_000_000.0
            return val
        return 1.0
        
    def korkuluk_hesapla(deger, urun):
        if pd.isna(deger): s = ""
        else: s = str(deger).lower().strip()
            
        if urun_makasli_mi(urun):
            if "sac" in s: return 1.75
            elif "tel" in s: return 1.3
            else: return 1.0
        else:
            if "sac" in s: return 1.75
            else: return 1.0

    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Ürün Çeşidi", "Çelik Durumu (1/0)", "Kapasite", "Metrekare", "Metrekare (m2)", "Teknik Puan", "Sipariş Başlangıç", "Sipariş Çıkış(Boya Hariç)", "Tezgah", "Operatörler", "Üretim Adedi", "Tel Fonk", "Bekleme Süresi (Gün)"]
    df = df[[col for col in hedef_sutunlar if col in df.columns]]

    df["Ürün Çeşidi"] = df["Ürün Çeşidi"].apply(urun_normalize)
    
    if "Tel Fonk" not in df.columns: df["Tel Fonk"] = "Tel"
    df["Korkuluk Çarpanı"] = df.apply(lambda row: korkuluk_hesapla(row["Tel Fonk"], row["Ürün Çeşidi"]), axis=1)
    df["Ham_Zorluk"] = df["Ürün Çeşidi"].apply(dinamik_zorluk) * df["Korkuluk Çarpanı"]

    df["Çelik Durumu (1/0)"] = pd.to_numeric(df.get("Çelik Durumu (1/0)", 0.0), errors='coerce').fillna(0.0)
    df["Çelik Çarpanı"] = df["Çelik Durumu (1/0)"] + 1.0
    
    df["Kapasite"] = df.get("Kapasite", pd.Series([1.0]*len(df))).apply(kapasite_ayikla).replace(0, 1.0)
    
    if "Metrekare (m2)" not in df.columns and "Metrekare" in df.columns: df["Metrekare (m2)"] = df["Metrekare"]
    df["Metrekare (m2)"] = df.get("Metrekare (m2)", pd.Series([1.0]*len(df))).apply(metrekare_ayikla).replace(0, 1.0)
    df["Teknik Puan"] = pd.to_numeric(df.get("Teknik Puan", 1.0), errors='coerce').fillna(1.0)
    
    df["Sipariş Başlangıç Tarihi"] = pd.to_datetime(df["Sipariş Başlangıç"], dayfirst=True, errors='coerce')
    df["Sipariş Çıkış Tarihi"] = pd.to_datetime(df["Sipariş Çıkış(Boya Hariç)"], dayfirst=True, errors='coerce')
    
    df["Toplam Süre (Gün)"] = (df["Sipariş Çıkış Tarihi"] - df["Sipariş Başlangıç Tarihi"]).dt.days
    
    if "Bekleme Süresi (Gün)" in df.columns:
        df["Bekleme Süresi (Gün)"] = pd.to_numeric(df["Bekleme Süresi (Gün)"], errors='coerce').fillna(0.0)
    else:
        df["Bekleme Süresi (Gün)"] = 0.0
        
    df["Net Üretim Süresi (Gün)"] = df["Toplam Süre (Gün)"] - df["Bekleme Süresi (Gün)"]
    df["Net Üretim Süresi (Gün)"] = df["Net Üretim Süresi (Gün)"].apply(lambda x: max(x, 1.0) if not pd.isna(x) else 1.0)

    # --- ZAMAN VERİMLİLİĞİ VE HIZ HESABI ---
    min_kap, max_kap = df["Kapasite"].min(), df["Kapasite"].max()
    df["Normalize_Kapasite"] = 1.0 if max_kap == min_kap else 1.0 + ((df["Kapasite"] - min_kap) / (max_kap - min_kap)) * (MAKSIMUM_CARPAN_KAPASITE - 1.0)
    
    makasli_mask_local = df["Ürün Çeşidi"].apply(urun_makasli_mi)
    min_m2, max_m2 = (df.loc[makasli_mask_local, "Metrekare (m2)"].min(), df.loc[makasli_mask_local, "Metrekare (m2)"].max()) if makasli_mask_local.any() else (1.0, 1.0)
    def m2_normalize_hesapla(row):
        if urun_makasli_mi(row["Ürün Çeşidi"]) and max_m2 > min_m2:
            return 1.0 + ((row["Metrekare (m2)"] - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0)
        return 1.0 
    df["Normalize_Metrekare"] = df.apply(m2_normalize_hesapla, axis=1)
    df["Normalize_Teknik"] = 1.0 + ((df["Teknik Puan"] - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
    
    min_ham_z = df["Ham_Zorluk"].min()
    max_ham_z = df["Ham_Zorluk"].max()
    if max_ham_z > min_ham_z:
        df["Zorluk Katsayısı"] = 1.0 + ((df["Ham_Zorluk"] - min_ham_z) / (max_ham_z - min_ham_z)) * (10.0 - 1.0)
    else:
        df["Zorluk Katsayısı"] = 1.0

    df["Ham_İş_Yükü"] = df['Zorluk Katsayısı'] * df['Normalize_Kapasite'] * df['Çelik Çarpanı'] * df['Normalize_Metrekare'] * df['Normalize_Teknik']
    df["Günlük_Hız"] = df["Ham_İş_Yükü"] / df["Net Üretim Süresi (Gün)"]
    
    fabrika_medyan_hiz = df["Günlük_Hız"].median()
    if pd.isna(fabrika_medyan_hiz) or fabrika_medyan_hiz == 0:
        fabrika_medyan_hiz = 1.0
        
    df["Zaman Verimlilik Çarpanı"] = (df["Günlük_Hız"] / fabrika_medyan_hiz).clip(lower=0.85, upper=1.15)

    df['Operatörler'] = df['Operatörler'].fillna('').astype(str)
    df['Kişi Sayısı'] = df['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1)
    df['Kişi Sayısı'] = df['Kişi Sayısı'].replace(0, 1)

    return df

# --- ÇİFTLİ YAPAY ZEKA MODELİ VE HATA METRİKLERİ ---
@st.cache_resource
def yapay_zeka_egit(df_model):
    X_cols = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Metrekare", "Normalize_Teknik", "Çelik Çarpanı", "Kişi Sayısı"]
    
    df_model = df_model.dropna(subset=["Net Üretim Süresi (Gün)", "Bekleme Süresi (Gün)"] + X_cols).copy()
    df_model = df_model[df_model["Net Üretim Süresi (Gün)"] > 0]
    
    if len(df_model) < 5: return None, None, None, None, None
    
    X = df_model[X_cols].values
    y_net = df_model["Net Üretim Süresi (Gün)"].values
    y_bekleme = df_model["Bekleme Süresi (Gün)"].values
    
    X_train, X_test, y_net_train, y_net_test = train_test_split(X, y_net, test_size=0.25, random_state=42)
    _, _, y_bek_train, y_bek_test = train_test_split(X, y_bekleme, test_size=0.25, random_state=42)
    
    sc = StandardScaler()
    X_train_scaled = sc.fit_transform(X_train)
    X_test_scaled = sc.transform(X_test)
    
    rf_net = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42)
    rf_net.fit(X_train_scaled, y_net_train)
    
    rf_bekleme = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42)
    rf_bekleme.fit(X_train_scaled, y_bek_train)
    
    # HATA METRİKLERİ (MAE, MSE, RMSE)
    y_net_pred = rf_net.predict(X_test_scaled)
    y_bek_pred = rf_bekleme.predict(X_test_scaled)
    
    metrikler = {
        "Net_MAE": mean_absolute_error(y_net_test, y_net_pred),
        "Net_RMSE": np.sqrt(mean_squared_error(y_net_test, y_net_pred)),
        "Bekleme_MAE": mean_absolute_error(y_bek_test, y_bek_pred),
        "Bekleme_RMSE": np.sqrt(mean_squared_error(y_bek_test, y_bek_pred)),
    }
    
    onem_yuzdeleri = rf_net.feature_importances_ * 100
    
    return rf_net, rf_bekleme, sc, onem_yuzdeleri, metrikler

# --- SIRALAMA FONKSİYONLARI ---
def aile_bazli_siralama(urun):
    u = str(urun).upper().strip()
    if "EAP" in u: prefix_score = 1
    elif "EEP" in u: prefix_score = 2
    elif "EYP" in u: prefix_score = 3
    elif "HYM" in u: prefix_score = 4
    elif "MAKASLI" in u: prefix_score = 5
    elif "KOLONLU" in u: prefix_score = 6
    elif "RAMPA" in u or "MENLİFT" in u: prefix_score = 7
    else: prefix_score = 8
    sayi_match = re.search(r'\d+', u)
    sayi = int(sayi_match.group()) if sayi_match else 0
    return (prefix_score, sayi, u)

def tezgah_siralama_anahtari(x):
    try: return (0, int(x))
    except:
        m = re.search(r'\d+', str(x))
        if m: return (0, int(m.group()))
        return (1, str(x))

# --- ANA UYGULAMA ---
try:
    df = veri_isle()
    
    if "Makaslı Üretimler" in secilen_kategori:
        df_kategori = df[df["Ürün Çeşidi"].apply(urun_makasli_mi)].copy()
    elif "Asansör ve Diğerleri" in secilen_kategori:
        df_kategori = df[~df["Ürün Çeşidi"].apply(urun_makasli_mi)].copy()
    else:
        df_kategori = df.copy()

    if df_kategori.empty:
        st.error("Bu kategoride hiç veri bulunamadı! Lütfen sol menüden başka bir kategori seçin.")
        st.stop()

    rf_net, rf_bekleme, sc, onem_yuzdeleri, model_metrikleri = yapay_zeka_egit(df_kategori)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Operatör & Tezgah Filtresi")
    
    tezgahlar_sirali = sorted(list(df_kategori["Tezgah"].dropna().unique()), key=tezgah_siralama_anahtari)
    secilen_tezgah = st.sidebar.selectbox("Tezgah Seçin", ["Tümü"] + tezgahlar_sirali)
    
    tum_operatorler = sorted(list(set(op.strip() for ops in df_kategori["Operatörler"].dropna() for op in ops.split(',') if op.strip())))
    secilen_operator = st.sidebar.selectbox("Operatör Seçin", ["Tümü"] + tum_operatorler)
    
    df_filtred = df_kategori.copy()
    if secilen_tezgah != "Tümü": df_filtred = df_filtred[df_filtred["Tezgah"] == secilen_tezgah]
    if secilen_operator != "Tümü": df_filtred = df_filtred[df_filtred["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ürün Analizi", "👷 Operatör Puanı", "🤖 Yapay Zeka Tahmini & Atama", "🏭 Fabrika Karakteristiği"])
    
    with tab1:
        st.subheader("Üretim Özeti")
        if "Makaslı Üretimler" in secilen_kategori: beklenen_urunler = [u for u in ZORLUK_HARITASI.keys() if urun_makasli_mi(u)]
        elif "Asansör ve Diğerleri" in secilen_kategori: beklenen_urunler = [u for u in ZORLUK_HARITASI.keys() if not urun_makasli_mi(u)]
        else: beklenen_urunler = list(ZORLUK_HARITASI.keys())
            
        base_df = pd.DataFrame({"Ürün Çeşidi": beklenen_urunler})
        base_df["Katsayı (Normalize 1-10)"] = base_df["Ürün Çeşidi"].map(ZORLUK_HARITASI)
        
        min_ham_z_global = df["Ham_Zorluk"].min()
        max_ham_z_global = df["Ham_Zorluk"].max()
        if max_ham_z_global > min_ham_z_global:
            base_df["Katsayı (Normalize 1-10)"] = base_df["Katsayı (Normalize 1-10)"].apply(lambda x: 1.0 + ((x - min_ham_z_global) / (max_ham_z_global - min_ham_z_global)) * (10.0 - 1.0) if not pd.isna(x) else 1.0)
            
        base_df["Toplam"] = 0
        base_df["Ortalama Üretim Adedi"] = 0.0
        base_df["Ortalama Toplam Süre (Gün)"] = 0.0
        base_df["Sipariş Sayısı"] = 0
        
        if not df_filtred.empty:
            grup_ozet = df_filtred.groupby(["Ürün Çeşidi"]).agg({
                "Zorluk Katsayısı": "mean",
                "Üretim Adedi": ["sum", "mean"], 
                "Toplam Süre (Gün)": "mean", 
                "Sipariş No": "count" if "Sipariş No" in df_filtred.columns else lambda x: len(x)
            }).reset_index()
            grup_ozet.columns = ["Ürün Çeşidi", "Katsayı (Normalize 1-10)", "Toplam", "Ortalama Üretim Adedi", "Ortalama Toplam Süre (Gün)", "Sipariş Sayısı"]
            merged_df = pd.concat([grup_ozet, base_df]).drop_duplicates(subset=["Ürün Çeşidi"], keep='first').reset_index(drop=True)
        else:
            merged_df = base_df
            
        merged_df["Toplam"] = merged_df["Toplam"].fillna(0).astype(int)
        merged_df["Sipariş Sayısı"] = merged_df["Sipariş Sayısı"].fillna(0).astype(int)
        merged_df["Katsayı (Normalize 1-10)"] = merged_df["Katsayı (Normalize 1-10)"].fillna(1.0).round(2)
        merged_df["Ortalama Üretim Adedi"] = merged_df["Ortalama Üretim Adedi"].fillna(0.0).round(2)
        merged_df["Ortalama Toplam Süre (Gün)"] = merged_df["Ortalama Toplam Süre (Gün)"].fillna(0.0).round(2)
        
        merged_df["Siralama_Anahtari"] = merged_df["Ürün Çeşidi"].apply(aile_bazli_siralama)
        merged_df = merged_df.sort_values(by=["Siralama_Anahtari"]).drop(columns=["Siralama_Anahtari"]).reset_index(drop=True)
        
        st.dataframe(merged_df, use_container_width=True)

    with tab2:
        st.subheader("👷 Operatör Performans Puanları (Gecikmelerden Arındırılmış & Hız Çarpanlı)")
        if not df_filtred.empty:
            df_op = df_filtred.copy()
            df_op['Operatörler'] = df_op['Operatörler'].str.split(',')
            df_op = df_op.explode('Operatörler')
            df_op['Operatörler'] = df_op['Operatörler'].str.strip()
            df_op = df_op[df_op['Operatörler'] != '']
            
            df_op['Toplam Puan'] = (
                df_op['Üretim Adedi'] * 
                df_op['Zorluk Katsayısı'] * 
                df_op['Normalize_Kapasite'] * 
                df_op['Çelik Çarpanı'] * 
                df_op['Normalize_Metrekare'] * 
                df_op['Normalize_Teknik'] * 
                df_op['Zaman Verimlilik Çarpanı']
            )
            df_op['Kişi Başı Puan'] = df_op['Toplam Puan'] / df_op['Kişi Sayısı']
            op_ozet = df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum", "Net Üretim Süresi (Gün)": "count"}).reset_index()
            op_ozet.rename(columns={"Net Üretim Süresi (Gün)": "Tamamlanan İş Sayısı"}, inplace=True)
            op_ozet["Kişi Başı Puan"] = round(op_ozet["Kişi Başı Puan"], 1)
            st.dataframe(op_ozet.sort_values(by="Kişi Başı Puan", ascending=False), use_container_width=True)
            
            global_op_puanlari = op_ozet.copy()

    with tab3:
        st.subheader("🔮 Makine Öğrenmesi Tahmini & İş Yükü Dengeleme (Yöneylem)")
        st.markdown("Yapay zeka modeli hem net imalat süresini hesaplar, hem istatistiksel hata metriklerini (MAE/RMSE) sunar, hem de yeni siparişin atölye içindeki **optimum operatör atamasını** yapar.")
        
        if rf_net is None:
            st.warning("Modeli eğitmek için bu kategoride yeterli sipariş geçmişi bulunamadı (En az 5 sipariş gerekli).")
        else:
            with st.expander("📈 Model Güvenilirliği ve Hata Analizi (Tıkla Genişlet)", expanded=False):
                st.markdown("Arka plandaki modelin test verisi üzerindeki istatistiksel sapma miktarlarıdır:")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown("**Net İmalat Modeli (Random Forest)**")
                    st.write(f"- **MAE (Ort. Mutlak Hata):** ± {model_metrikleri['Net_MAE']:.2f} Gün")
                    st.write(f"- **RMSE (Kök Ort. Kare Hata):** ± {model_metrikleri['Net_RMSE']:.2f} Gün")
                with col_m2:
                    st.markdown("**Bekleme/Gecikme Modeli (Random Forest)**")
                    st.write(f"- **MAE (Ort. Mutlak Hata):** ± {model_metrikleri['Bekleme_MAE']:.2f} Gün")
                    st.write(f"- **RMSE (Kök Ort. Kare Hata):** ± {model_metrikleri['Bekleme_RMSE']:.2f} Gün")

            st.markdown("---")
            col1, col2 = st.columns(2)
            dinamik_urunler = sorted(df_kategori["Ürün Çeşidi"].unique().tolist(), key=aile_bazli_siralama)
            if not dinamik_urunler: dinamik_urunler = sorted(list(ZORLUK_HARITASI.keys()), key=aile_bazli_siralama)
            
            with col1:
                input_urun = st.selectbox("Ürün Çeşidi", dinamik_urunler)
                input_kapasite = st.number_input("Kapasite (Ton/Adet)", value=1.0, min_value=0.1)
                
                # --- YENİ EKLENEN: TEXT INPUT İLE EBAT GİRİŞİ ---
                input_m2_str = st.text_input("Ebat (mm*mm veya m²)", value="5000", help="Milimetre cinsinden (Örn: 2000*7821) veya doğrudan m² girebilirsiniz.")
                
                if urun_makasli_mi(input_urun):
                    input_telfonk = st.selectbox("Tel Fonk / Kaplama", ["Düz (Standart)", "Tel", "Sac"])
                else:
                    input_telfonk = st.selectbox("Tel Fonk / Kaplama", ["Tel / Yok (Standart)", "Sac"])

            with col2:
                input_kisi = st.number_input("Ekipteki Operatör Sayısı", min_value=1, value=1)
                input_teknik = st.slider("Teknik Zorluk Puanı", min_value=1.0, max_value=10.0, value=1.0)
                input_celik = st.selectbox("Çelik Durumu (0: Yok, 1: Var)", [0, 1])
                
            if st.button("🚀 Tahmin Et & Operatör Öner", type="primary"):
                # --- EBAT METNİNİ ÇÖZÜMLEYİP M2 HESAPLAYAN YENİ BLOK ---
                s_m2 = str(input_m2_str).lower().replace(' ', '').replace(',', '.')
                m2_deger = 1.0
                parcalar = re.split(r'[\*x]', s_m2)
                if len(parcalar) == 2:
                    try:
                        en = float(re.search(r'[\d\.]+', parcalar[0]).group())
                        boy = float(re.search(r'[\d\.]+', parcalar[1]).group())
                        m2_deger = (en * boy) / 1_000_000.0
                    except: pass
                else:
                    match = re.search(r'[\d\.]+', s_m2)
                    if match:
                        val = float(match.group())
                        m2_deger = (val / 1_000_000.0) if val > 100 else val

                def dinamik_zorluk_manuel(urun):
                    urun_str = str(urun).upper()
                    if urun_str in ZORLUK_HARITASI: base_v = ZORLUK_HARITASI[urun_str]
                    elif any(kod in urun_str for kod in ["EYP", "HYM", "EEP", "EAP"]): base_v = 2.5
                    elif "ÖZEL" in urun_str or "OZEL" in urun_str: base_v = 3.0
                    else: base_v = 1.5
                    
                    if urun_makasli_mi(urun):
                        t_carp = 1.75 if input_telfonk == "Sac" else (1.3 if input_telfonk == "Tel" else 1.0)
                    else:
                        t_carp = 1.75 if input_telfonk == "Sac" else 1.0
                    
                    ham = base_v * t_carp
                    min_ham_z = df["Ham_Zorluk"].min()
                    max_ham_z = df["Ham_Zorluk"].max()
                    if max_ham_z > min_ham_z:
                        return 1.0 + ((ham - min_ham_z) / (max_ham_z - min_ham_z)) * (10.0 - 1.0)
                    return 1.0
                    
                norm_zorluk = dinamik_zorluk_manuel(input_urun)
                min_kap = df["Kapasite"].min()
                max_kap = df["Kapasite"].max()
                norm_kapasite = 1.0 + ((input_kapasite - min_kap) / (max_kap - min_kap)) * (MAKSIMUM_CARPAN_KAPASITE - 1.0) if max_kap > min_kap else 1.0
                
                makasli_mask = df["Ürün Çeşidi"].apply(urun_makasli_mi)
                min_m2, max_m2 = (df.loc[makasli_mask, "Metrekare (m2)"].min(), df.loc[makasli_mask, "Metrekare (m2)"].max()) if makasli_mask.any() else (1.0, 1.0)
                
                # m2_deger yukarıda akıllı ayrıştırıcı ile zaten m2'ye çevrildi
                norm_m2 = 1.0 + ((m2_deger - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0) if urun_makasli_mi(input_urun) and max_m2 > min_m2 else 1.0
                
                norm_teknik = 1.0 + ((input_teknik - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
                celik_carp = input_celik + 1.0
                
                ham_veri = np.array([[norm_zorluk, norm_kapasite, norm_m2, norm_teknik, celik_carp, input_kisi]])
                veri_scaled = sc.transform(ham_veri)
                
                tahmini_net_gun = max(rf_net.predict(veri_scaled)[0], 1.0)
                tahmini_bekleme_gun = max(rf_bekleme.predict(veri_scaled)[0], 0.0)
                toplam_tahmin_gun = tahmini_net_gun + tahmini_bekleme_gun
                
                st.success(f"### 🎯 Toplam Tahmini Teslimat Süresi: **{toplam_tahmin_gun:.1f} Gün**")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("🛠️ Tahmini Net İmalat Süresi", f"{tahmini_net_gun:.1f} Gün")
                with col_b:
                    st.metric("⏳ Tahmini Bekleme / Tedarik Süresi", f"{tahmini_bekleme_gun:.1f} Gün")
                
                st.markdown("---")
                st.markdown("### 🔄 Yöneylem & İş Yükü Dengeleme (Atama Tavsiyesi)")
                
                df_uzman = df_op[df_op["Ürün Çeşidi"] == input_urun]
                if not df_uzman.empty:
                    en_hizli_op = df_uzman.groupby("Operatörler")["Net Üretim Süresi (Gün)"].mean().idxmin()
                    en_hizli_sure = df_uzman.groupby("Operatörler")["Net Üretim Süresi (Gün)"].mean().min()
                    st.info(f"🏆 **Hız ve Uzmanlık Tavsiyesi:** Bu sipariş tipi için en tecrübeli/hızlı operatör **{en_hizli_op}** (Ortalama {en_hizli_sure:.1f} günde tamamlıyor). Hızlı çıkması gereken acil bir siparişse ona atanması önerilir.")
                else:
                    st.info("🏆 **Hız ve Uzmanlık Tavsiyesi:** Bu ürün tipi için geçmişte net bir operatör verisi bulunamadı.")
                
                if 'global_op_puanlari' in locals() and not global_op_puanlari.empty:
                    aktif_operatörler = global_op_puanlari[global_op_puanlari["Tamamlanan İş Sayısı"] >= 2]
                    if not aktif_operatörler.empty:
                        en_musait_op = aktif_operatörler.loc[aktif_operatörler["Kişi Başı Puan"].idxmin()]["Operatörler"]
                        st.success(f"⚖️ **Kapasite ve İş Yükü Tavsiyesi:** Atölye genelinde anlık iş yükü/performans puanı en düşük olan kişi **{en_musait_op}**. Fabrika içi adil iş dağılımı (Line Balancing) için siparişin bu operatöre atanması önerilir.")

    with tab4:
        st.subheader("🏭 Genel Üretim Karakteristiği")
        st.markdown("Bu grafik, Google E-Tablo üzerinden çekilen net verilerle oluşturulmuştur.")
        if rf_net is not None:
            fig_genel, ax_genel = plt.subplots(figsize=(8, 3.5))
            etiketler_genel = ["Ürün Zorluğu (1-10)", "Kapasite", "Ebat (m²)", "Teknik Puan", "Çelik Durumu", "Ekip Sayısı"]
            sirali_indeksler_g = np.argsort(onem_yuzdeleri)[::-1]
            sirali_yuzdeler_g = onem_yuzdeleri[sirali_indeksler_g]
            sirali_etiketler_g = [etiketler_genel[i] for i in sirali_indeksler_g]
            ax_genel.barh(sirali_etiketler_g[::-1], sirali_yuzdeler_g[::-1], color='darkorange', edgecolor='black')
            ax_genel.set_xlabel("Genel Etki Yüzdesi (%)")
            for index, value in enumerate(sirali_yuzdeler_g[::-1]):
                ax_genel.text(value + 0.5, index, f"%{value:.1f}", va='center')
            st.pyplot(fig_genel)

except Exception as e: st.error(f"Bir hata oluştu: {e}")
