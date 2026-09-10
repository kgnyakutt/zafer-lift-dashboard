import pandas as pd
import numpy as np
import re
import streamlit as st
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import warnings
warnings.filterwarnings("ignore")

# Sayfa Yapılandırması
st.set_page_config(page_title="Zafer Lift - Üretim ve Performans Panosu", layout="wide")

st.title("🚀 Zafer Lift Makine - Üretim Kapasitesi ve Operatör Performans Panosu")
st.markdown("Bu pano, şirket içi pilot veriler baz alınarak Python altyapısıyla dinamik olarak oluşturulmuştur.")

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

MAKSIMUM_CARPAN_TONAJ = 2.0   
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

# --- KENAR ÇUBUĞU DOSYA VE KATEGORİ YÖNETİMİ ---
st.sidebar.header("📁 Veri Yönetimi")
yuklenen_dosya = st.sidebar.file_uploader("Excel Dosyası Yükle (.xlsx)", type=["xlsx"])

st.sidebar.markdown("---")
st.sidebar.header("🏗️ Üretim Kategorisi")
secilen_kategori = st.sidebar.radio(
    "Hangi üretim tipini incelemek istiyorsunuz?",
    ["Tümü (Genel Analiz)", "Makaslı Üretimler (Makaslılar, EYP, EEP vb.)", "Asansör ve Diğerleri (Kolonlu, HYM, Rampa vb.)"]
)

# --- VERİ İŞLEME ---
@st.cache_data
def veri_isle(dosya_kaynagi):
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

    def tonaj_ayikla(deger):
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
        if match: return float(match.group())
        return 1.0
        
    def korkuluk_hesapla(deger, urun):
        if pd.isna(deger): 
            s = ""
        else:
            s = str(deger).lower().strip()
            
        if urun_makasli_mi(urun):
            if "sac" in s: return 1.75
            elif "tel" in s: return 1.3
            else: return 1.0
        else:
            if "sac" in s: return 1.75
            else: return 1.0

    if dosya_kaynagi is not None: df = pd.read_excel(dosya_kaynagi)
    else: df = pd.read_excel("personel_listesi.xlsx") 
        
    df.columns = df.columns.str.strip()
    hedef_sutunlar = ["Sipariş No", "Ürün Çeşidi", "Çelik Durumu (1/0)", "Tonaj", "Metrekare", "Metrekare (m2)", "Teknik Puan", "Sipariş Başlangıç", "Sipariş Çıkış(Boya Hariç)", "Tezgah", "Operatörler", "Üretim Adedi", "Korkuluk Kaplama"]
    df = df[[col for col in hedef_sutunlar if col in df.columns]]

    df["Ürün Çeşidi"] = df["Ürün Çeşidi"].apply(urun_normalize)
    
    if "Korkuluk Kaplama" not in df.columns:
        df["Korkuluk Kaplama"] = "Tel"
    df["Korkuluk Çarpanı"] = df.apply(lambda row: korkuluk_hesapla(row["Korkuluk Kaplama"], row["Ürün Çeşidi"]), axis=1)
    df["Zorluk Katsayısı"] = df["Ürün Çeşidi"].apply(dinamik_zorluk) * df["Korkuluk Çarpanı"]

    df["Çelik Durumu (1/0)"] = pd.to_numeric(df.get("Çelik Durumu (1/0)", 0.0), errors='coerce').fillna(0.0)
    df["Çelik Çarpanı"] = df["Çelik Durumu (1/0)"] + 1.0
    df["Tonaj"] = df.get("Tonaj", pd.Series([1.0]*len(df))).apply(tonaj_ayikla).replace(0, 1.0)
    
    if "Metrekare (m2)" not in df.columns and "Metrekare" in df.columns: df["Metrekare (m2)"] = df["Metrekare"]
    df["Metrekare (m2)"] = df.get("Metrekare (m2)", pd.Series([1.0]*len(df))).apply(metrekare_ayikla).replace(0, 1.0)
    df["Teknik Puan"] = pd.to_numeric(df.get("Teknik Puan", 1.0), errors='coerce').fillna(1.0)
    
    df["Sipariş Başlangıç Tarihi"] = pd.to_datetime(df["Sipariş Başlangıç"], dayfirst=True, errors='coerce')
    df["Sipariş Çıkış Tarihi"] = pd.to_datetime(df["Sipariş Çıkış(Boya Hariç)"], dayfirst=True, errors='coerce')
    df["Teslim Süresi (Gün)"] = (df["Sipariş Çıkış Tarihi"] - df["Sipariş Başlangıç Tarihi"]).dt.days
    df['Operatörler'] = df['Operatörler'].fillna('').astype(str)
    df['Kişi Sayısı'] = df['Operatörler'].apply(lambda x: len([op for op in x.split(',') if op.strip()]) if x else 1)
    df['Kişi Sayısı'] = df['Kişi Sayısı'].replace(0, 1)

    return df

# --- MAKİNE ÖĞRENMESİ MODELİ & ETKİ ANALİZİ ---
@st.cache_resource
def yapay_zeka_egit(df_model):
    X_cols = ["Zorluk Katsayısı", "Normalize_Tonaj", "Normalize_Metrekare", "Normalize_Teknik", "Çelik Çarpanı", "Kişi Sayısı"]
    Y_col = "Teslim Süresi (Gün)"
    df_model = df_model.dropna(subset=[Y_col] + X_cols).copy()
    df_model = df_model[df_model[Y_col] > 0]
    
    if len(df_model) < 5: return None, None, None, None
    X = df_model[X_cols].values
    y = df_model[Y_col].values
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
    sc = StandardScaler()
    X_train_scaled = sc.fit_transform(X_train)
    rf_model = RandomForestRegressor(n_estimators=100, max_features='sqrt', random_state=42)
    rf_model.fit(X_train_scaled, y_train)
    onem_yuzdeleri = rf_model.feature_importances_ * 100
    poly = PolynomialFeatures(degree=2, include_bias=False)
    regressor = LinearRegression()
    X_train_poly = poly.fit_transform(X_train_scaled)
    regressor.fit(X_train_poly, y_train)
    return regressor, sc, poly, onem_yuzdeleri

# --- YENİ EKLENEN: DOĞAL SIRALAMA (NATURAL SORT) FONKSİYONU ---
def dogal_siralama_anahtari(x):
    # Bu fonksiyon kelimelerin içindeki sayıları bütün olarak algılar.
    # Örneğin: EYP2, EYP10'dan önce gelir.
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(x))]
# ----------------------------------------------------------------

# --- ANA UYGULAMA ---
try:
    df_raw = veri_isle(yuklenen_dosya)
    
    if "Makaslı Üretimler" in secilen_kategori:
        df = df_raw[df_raw["Ürün Çeşidi"].apply(urun_makasli_mi)].copy()
    elif "Asansör ve Diğerleri" in secilen_kategori:
        df = df_raw[~df_raw["Ürün Çeşidi"].apply(urun_makasli_mi)].copy()
    else:
        df = df_raw.copy()

    if not df.empty:
        min_tonaj, max_tonaj = df["Tonaj"].min(), df["Tonaj"].max()
        df["Normalize_Tonaj"] = 1.0 if max_tonaj == min_tonaj else 1.0 + ((df["Tonaj"] - min_tonaj) / (max_tonaj - min_tonaj)) * (MAKSIMUM_CARPAN_TONAJ - 1.0)
        makasli_mask_local = df["Ürün Çeşidi"].apply(urun_makasli_mi)
        min_m2, max_m2 = (df.loc[makasli_mask_local, "Metrekare (m2)"].min(), df.loc[makasli_mask_local, "Metrekare (m2)"].max()) if makasli_mask_local.any() else (1.0, 1.0)
        def m2_normalize_hesapla(row):
            if urun_makasli_mi(row["Ürün Çeşidi"]) and max_m2 > min_m2:
                return 1.0 + ((row["Metrekare (m2)"] - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0)
            return 1.0 
        df["Normalize_Metrekare"] = df.apply(m2_normalize_hesapla, axis=1)
        df["Normalize_Teknik"] = 1.0 + ((df["Teknik Puan"] - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
    else:
        st.error("Bu kategoride hiç veri bulunamadı! Lütfen sol menüden başka bir kategori seçin.")
        st.stop()

    regressor, sc, poly, onem_yuzdeleri = yapay_zeka_egit(df)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Operatör & Tezgah Filtresi")
    secilen_tezgah = st.sidebar.selectbox("Tezgah Seçin", ["Tümü"] + list(df["Tezgah"].dropna().unique()))
    tum_operatorler = set(op.strip() for ops in df["Operatörler"].dropna() for op in ops.split(',') if op.strip())
    secilen_operator = st.sidebar.selectbox("Operatör Seçin", ["Tümü"] + sorted(list(tum_operatorler)))
    
    df_filtred = df.copy()
    if secilen_tezgah != "Tümü": df_filtred = df_filtred[df_filtred["Tezgah"] == secilen_tezgah]
    if secilen_operator != "Tümü": df_filtred = df_filtred[df_filtred["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ürün Analizi", "👷 Operatör Puanı", "🤖 Yapay Zeka Tahmini", "🏭 Fabrika Karakteristiği"])
    
    with tab1:
        st.subheader("Üretim Özeti")
        if "Makaslı Üretimler" in secilen_kategori:
            beklenen_urunler = [u for u in ZORLUK_HARITASI.keys() if urun_makasli_mi(u)]
        elif "Asansör ve Diğerleri" in secilen_kategori:
            beklenen_urunler = [u for u in ZORLUK_HARITASI.keys() if not urun_makasli_mi(u)]
        else:
            beklenen_urunler = list(ZORLUK_HARITASI.keys())
            
        base_df = pd.DataFrame({"Ürün Çeşidi": beklenen_urunler})
        base_df["Katsayı (Ortalama)"] = base_df["Ürün Çeşidi"].map(ZORLUK_HARITASI)
        base_df["Toplam"] = 0
        base_df["Ortalama"] = 0.0
        base_df["Ortalama Süre (Gün)"] = 0.0
        base_df["Sipariş Sayısı"] = 0
        
        if not df_filtred.empty:
            grup_ozet = df_filtred.groupby(["Ürün Çeşidi"]).agg({
                "Zorluk Katsayısı": "mean",
                "Üretim Adedi": ["sum", "mean"], 
                "Teslim Süresi (Gün)": "mean", 
                "Sipariş No": "count" if "Sipariş No" in df_filtred.columns else lambda x: len(x)
            }).reset_index()
            grup_ozet.columns = ["Ürün Çeşidi", "Katsayı (Ortalama)", "Toplam", "Ortalama", "Ortalama Süre (Gün)", "Sipariş Sayısı"]
            merged_df = pd.concat([grup_ozet, base_df]).drop_duplicates(subset=["Ürün Çeşidi"], keep='first').reset_index(drop=True)
        else:
            merged_df = base_df
            
        merged_df["Toplam"] = merged_df["Toplam"].fillna(0).astype(int)
        merged_df["Sipariş Sayısı"] = merged_df["Sipariş Sayısı"].fillna(0).astype(int)
        merged_df["Katsayı (Ortalama)"] = merged_df["Katsayı (Ortalama)"].fillna(1.0).round(2)
        merged_df["Ortalama"] = merged_df["Ortalama"].fillna(0.0).round(2)
        merged_df["Ortalama Süre (Gün)"] = merged_df["Ortalama Süre (Gün)"].fillna(0.0).round(2)
        
        # TABLO 1: ÜRÜN İSMİNE GÖRE DOĞAL SIRALAMA (EAP1, EAP2, EEP1, EYP1, EYP2...)
        merged_df["Siralama_Anahtari"] = merged_df["Ürün Çeşidi"].apply(dogal_siralama_anahtari)
        merged_df = merged_df.sort_values(by=["Siralama_Anahtari"]).drop(columns=["Siralama_Anahtari"]).reset_index(drop=True)
        
        st.dataframe(merged_df, use_container_width=True)

    with tab2:
        st.subheader("Operatör Performans Puanları")
        if not df_filtred.empty:
            df_op = df_filtred.copy()
            df_op['Operatörler'] = df_op['Operatörler'].str.split(',')
            df_op = df_op.explode('Operatörler')
            df_op['Operatörler'] = df_op['Operatörler'].str.strip()
            df_op = df_op[df_op['Operatörler'] != '']
            df_op['Toplam Puan'] = (df_op['Üretim Adedi'] * df_op['Zorluk Katsayısı'] * df_op['Normalize_Tonaj'] * df_op['Çelik Çarpanı'] * df_op['Normalize_Metrekare'] * df_op['Normalize_Teknik'])
            df_op['Kişi Başı Puan'] = df_op['Toplam Puan'] / df_op['Kişi Sayısı']
            op_ozet = df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum"}).reset_index()
            op_ozet["Kişi Başı Puan"] = round(op_ozet["Kişi Başı Puan"], 1)
            st.dataframe(op_ozet.sort_values(by="Kişi Başı Puan", ascending=False), use_container_width=True)

    with tab3:
        st.subheader("🔮 Makine Öğrenmesi Tahmini")
        st.markdown("Arka plandaki Yapay Zeka modeli, şu an sadece sol menüde seçtiğiniz kategoriye ait geçmiş siparişleri baz alarak optimize edilmiştir.")
        if regressor is None:
            st.warning("Modeli eğitmek için bu kategoride yeterli sipariş geçmişi bulunamadı (En az 5 sipariş gerekli).")
        else:
            col1, col2 = st.columns(2)
            
            # SEÇME KUTUSU (DROPDOWN) İÇİN DE DOĞAL SIRALAMA
            dinamik_urunler = sorted(df["Ürün Çeşidi"].unique().tolist(), key=dogal_siralama_anahtari)
            if not dinamik_urunler: 
                dinamik_urunler = sorted(list(ZORLUK_HARITASI.keys()), key=dogal_siralama_anahtari)
            
            with col1:
                input_urun = st.selectbox("Ürün Çeşidi", dinamik_urunler)
                input_tonaj = st.number_input("Tonaj (Ton)", value=1.0, min_value=0.1)
                input_m2 = st.number_input("Ebat (Metrekare)", value=1.0, min_value=0.1)
                
                if urun_makasli_mi(input_urun):
                    input_korkuluk = st.selectbox("Korkuluk Kaplama", ["Düz (Standart)", "Tel", "Sac"])
                else:
                    input_korkuluk = st.selectbox("Korkuluk Kaplama", ["Tel / Yok (Standart)", "Sac"])

            with col2:
                input_kisi = st.number_input("Ekipteki Operatör Sayısı", min_value=1, value=1)
                input_teknik = st.slider("Teknik Zorluk Puanı", min_value=1.0, max_value=10.0, value=1.0)
                input_celik = st.selectbox("Çelik Durumu (0: Yok, 1: Var)", [0, 1])
                
            if st.button("🚀 Üretim Süresini Tahmin Et ve Analiz Çıkar", type="primary"):
                def dinamik_zorluk_manuel(urun):
                    urun_str = str(urun).upper()
                    if urun_str in ZORLUK_HARITASI: return ZORLUK_HARITASI[urun_str]
                    if any(kod in urun_str for kod in ["EYP", "HYM", "EEP", "EAP"]): return 2.5
                    if "ÖZEL" in urun_str or "OZEL" in urun_str:
                        if "MAKASLI" in urun_str: return 6.5
                        elif "KOLONLU" in urun_str: return 6.0
                        return 3.0
                    return 1.5
                    
                ham_zorluk = dinamik_zorluk_manuel(input_urun)
                
                if urun_makasli_mi(input_urun):
                    if input_korkuluk == "Sac": korkuluk_carp = 1.75
                    elif input_korkuluk == "Tel": korkuluk_carp = 1.3
                    else: korkuluk_carp = 1.0
                else:
                    if input_korkuluk == "Sac": korkuluk_carp = 1.75
                    else: korkuluk_carp = 1.0
                    
                birlesik_zorluk = ham_zorluk * korkuluk_carp
                
                norm_tonaj = 1.0 + ((input_tonaj - min_tonaj) / (max_tonaj - min_tonaj)) * (MAKSIMUM_CARPAN_TONAJ - 1.0) if max_tonaj > min_tonaj else 1.0
                norm_m2 = 1.0 + ((input_m2 - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0) if urun_makasli_mi(input_urun) and max_m2 > min_m2 else 1.0
                norm_teknik = 1.0 + ((input_teknik - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)
                celik_carp = input_celik + 1.0
                
                ham_veri = np.array([[birlesik_zorluk, norm_tonaj, norm_m2, norm_teknik, celik_carp, input_kisi]])
                veri_scaled = sc.transform(ham_veri)
                veri_poly = poly.transform(veri_scaled)
                tahmini_gun = max(regressor.predict(veri_poly)[0], 1.0)
                st.success(f"### 🎉 Beklenen Üretim Süresi: **{tahmini_gun:.1f} Gün**")
                
                yerel_carpanlar = np.array([birlesik_zorluk, norm_tonaj, norm_m2, norm_teknik, celik_carp, (3.0 / input_kisi)])
                yerel_etkiler = yerel_carpanlar * onem_yuzdeleri
                yerel_yuzdeler = (yerel_etkiler / np.sum(yerel_etkiler)) * 100
                
                etiketler = ["Ürün Zorluğu (Korkuluk Dahil)", "Tonaj", "Ebat (m²)", "Teknik Detaylar", "Çelik Kullanımı", "Ekip Yetersizliği"]
                
                st.markdown("---")
                st.subheader("🎯 Bu Makineyi En Çok Ne Yavaşlatıyor?")
                fig, ax = plt.subplots(figsize=(8, 3))
                sirali_indeksler = np.argsort(yerel_yuzdeler)[::-1]
                sirali_yuzdeler = yerel_yuzdeler[sirali_indeksler]
                sirali_etiketler = [etiketler[i] for i in sirali_indeksler]
                renkler = ['crimson' if i == 0 else 'steelblue' for i in range(len(sirali_yuzdeler))]
                ax.barh(sirali_etiketler[::-1], sirali_yuzdeler[::-1], color=renkler[::-1], edgecolor='black')
                ax.set_xlabel("Siparişe Etki Yüzdesi (%)")
                for index, value in enumerate(sirali_yuzdeler[::-1]):
                    ax.text(value + 0.5, index, f"%{value:.1f}", va='center')
                st.pyplot(fig)
                
                en_buyuk_etken = sirali_etiketler[0]
                st.markdown("### 🤖 Yapay Zeka Tavsiyesi:")
                if en_buyuk_etken == "Teknik Detaylar": st.warning("Bu siparişin süresini en çok **Teknik Detayların (Puanın) yüksekliği** uzatıyor. Üretime tecrübeli ustaların atanması önerilir.")
                elif en_buyuk_etken == "Ekip Yetersizliği": st.warning(f"Süreyi en çok **Ekip Sayısının ({input_kisi} kişi) az olması** uzatıyor. Operatör eklerseniz üretim ciddi oranda hızlanır.")
                elif en_buyuk_etken == "Tonaj": st.info("Bu siparişte **Tonaj (Ağırlık) kaynaklı** süre artışı var. Atölyedeki vinç hatlarının rezerve edilmesi önerilir.")
                elif en_buyuk_etken == "Ürün Zorluğu (Korkuluk Dahil)": 
                    st.info(f"Süreyi en çok **{input_urun}** şasisinin ve seçtiğiniz **{input_korkuluk}** kaplamasının birleşik zorluğu etkiliyor. Kalıp, aparat ve özellikle sac/tel işçiliği hazırlıklarını erkenden başlatın.")
                elif en_buyuk_etken == "Çelik Kullanımı": st.info("Çelik kullanımı kaynak sürelerini uzatmaktadır. Kaynak istasyonlarının hazır bulunduğundan emin olun.")
                else: st.success("Sipariş parametreleri oldukça dengeli görünüyor.")

    with tab4:
        st.subheader("🏭 Genel Üretim Karakteristiği")
        st.markdown("Bu grafik, sol menüden seçtiğiniz üretim grubuna ait geçmiş siparişlerin analizini gösterir.")
        if regressor is not None:
            fig_genel, ax_genel = plt.subplots(figsize=(8, 3.5))
            etiketler_genel = ["Ürün Zorluğu (Korkuluk Dahil)", "Tonaj", "Ebat (m²)", "Teknik Puan", "Çelik Durumu", "Ekip Sayısı"]
            sirali_indeksler_g = np.argsort(onem_yuzdeleri)[::-1]
            sirali_yuzdeler_g = onem_yuzdeleri[sirali_indeksler_g]
            sirali_etiketler_g = [etiketler_genel[i] for i in sirali_indeksler_g]
            ax_genel.barh(sirali_etiketler_g[::-1], sirali_yuzdeler_g[::-1], color='darkorange', edgecolor='black')
            ax_genel.set_xlabel("Genel Etki Yüzdesi (%)")
            for index, value in enumerate(sirali_yuzdeler_g[::-1]):
                ax_genel.text(value + 0.5, index, f"%{value:.1f}", va='center')
            st.pyplot(fig_genel)

except ValueError as ve: st.warning(f"⚠️ Dosya Yükleme Hatası: {ve}")
except Exception as e: st.error(f"Bir hata oluştu: {e}")
