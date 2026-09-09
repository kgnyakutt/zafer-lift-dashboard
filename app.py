import pandas as pd
import re
import streamlit as st
import matplotlib.pyplot as plt

# Sayfa Yapılandırması
st.set_page_config(page_title="Zafer Lift - Üretim ve Performans Panosu", layout="wide")

st.title("🚀 Zafer Lift Makine - Üretim Kapasitesi ve Operatör Performans Panosu")
st.markdown("Bu pano, şirket içi pilot veriler baz alınarak Python altyapısıyla dinamik olarak oluşturulmuştur.")

# --- KENAR ÇUBUĞU (SİDEBAR) DOSYA YÜKLEME ALANI ---
st.sidebar.header("📁 Veri Yönetimi")
yuklenen_dosya = st.sidebar.file_uploader("Excel Dosyası Yükle (.xlsx)", type=["xlsx"])

# Veri Okuma ve İşleme Fonksiyonu
@st.cache_data
def veri_isle(dosya_kaynagi):
    def urun_normalize(deger):
        if pd.isna(deger):
            return deger
        s = str(deger).strip().upper()
        s = re.sub(r'[\s\.\-]+', '', s)
        return s

    def tonaj_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '':
            return 1.0
        s = str(deger).lower().replace(',', '.')
        match = re.search(r'[\d\.]+', s)
        if match:
            sayi = float(match.group())
            if sayi > 50 or "kg" in s:
                return sayi / 1000.0
            return sayi
        return 1.0

    def metrekare_ayikla(deger):
        if pd.isna(deger) or str(deger).strip() == '':
            return 1.0
        s = str(deger).lower().replace(' ', '').replace(',', '.')
        parcalar = re.split(r'[\*x]', s)
        if len(parcalar) == 2:
            try:
                en = float(re.search(r'[\d\.]+', parcalar[0]).group())
                boy = float(re.search(r'[\d\.]+', parcalar[1]).group())
                return (en * boy) / 1_000_000.0
            except:
                pass
        match = re.search(r'[\d\.]+', s)
        if match:
            return float(match.group())
        return 1.0

    # Excel'i Oku
    if dosya_kaynagi is not None:
        df = pd.read_excel(dosya_kaynagi)
    else:
        df = pd.read_excel("personel_listesi.xlsx")
        
    df.columns = df.columns.str.strip()

    # --- YENİ: GEREKSİZ SÜTUNLARI ÇÖPE ATMA (SUBSETTING) ---
    # Sadece analizde kullanacağımız potansiyel sütunları tanımlıyoruz.
    hedef_sutunlar = [
        "Sipariş No", "Ürün Çeşidi", "Çelik Durumu (1/0)", "Tonaj", 
        "Metrekare", "Metrekare (m2)", "Teknik Puan", "Sipariş Başlangıç", 
        "Sipariş Çıkış(Boya Hariç)", "Tezgah", "Operatörler", "Üretim Adedi"
    ]
    # Yüklenen Excel'de bu sütunlardan hangileri varsa sadece onları al (Seri No, Strok vb. dışarıda kalır)
    mevcut_sutunlar = [col for col in hedef_sutunlar if col in df.columns]
    df = df[mevcut_sutunlar]
    # --------------------------------------------------------

    # Zorunlu sütun kontrolü (Uygulamanın çökmesini engeller)
    zorunlu_sutunlar = ["Ürün Çeşidi", "Tezgah", "Operatörler", "Üretim Adedi", "Sipariş Başlangıç", "Sipariş Çıkış(Boya Hariç)"]
    eksik_sutunlar = [s for s in zorunlu_sutunlar if s not in df.columns]
    if eksik_sutunlar:
        raise ValueError(f"Yüklenen Excel dosyasında şu zorunlu sütunlar eksik: {', '.join(eksik_sutunlar)}")

    df["Ürün Çeşidi"] = df["Ürün Çeşidi"].apply(urun_normalize)
    
    zorluk_haritasi = {
        "EYP1Ç": 1.0, "HYM2": 1.0, "HYM1": 1.0, "HYM2EAP": 1.0, "HR": 1.0,
        "EYP2": 1.0, "EYP3": 1.0, "EYP1": 1.0, "EAP2": 1.0, "EYP1U": 1.0,
        "EYP4": 1.0, "EYP1S12": 1.0, "EYP1S11": 1.0, "EAP1": 1.0, "EYP1T": 1.0,
        "EEP3": 1.0, "EYP1H": 1.0, "EYP1A": 1.0, "EEP2": 1.0, "EEP1": 1.0,
        "EYP1A": 1.0, "PYM157ÖZEL": 1.0, "HYM2T": 1.0, "HYM4": 1.0, "EYP2H": 1.0,
        "DÜZRAMPA": 1.0, "MENTEŞELİRAMPA": 2.0, "MENLİFT": 2.5, 
        "1MAKASLI": 3.0, "2MAKASLI": 4.5, "3MAKASLI": 6.0,
        "1KOLONLU": 3.5, "2KOLONLU": 5.0, "4KOLONLU": 8.0,
        "ENGELLİRAMPASI": 1.0
    }
    df["Zorluk Katsayısı"] = df["Ürün Çeşidi"].map(zorluk_haritasi).fillna(1.0)

    if "Çelik Durumu (1/0)" not in df.columns: 
        df["Çelik Durumu (1/0)"] = 0.0
    else: 
        df["Çelik Durumu (1/0)"] = pd.to_numeric(df["Çelik Durumu (1/0)"], errors='coerce').fillna(0.0)
    df["Çelik Çarpanı"] = df["Çelik Durumu (1/0)"] + 1.0

    MAKSIMUM_CARPAN_TONAJ = 2.0   
    MAKSIMUM_CARPAN_M2 = 1.3       
    MAKSIMUM_CARPAN_TEKNIK = 1.5   
    
    if "Tonaj" not in df.columns: 
        df["Tonaj"] = 1.0
    else: 
        df["Tonaj"] = df["Tonaj"].apply(tonaj_ayikla).replace(0, 1.0)

    min_tonaj, max_tonaj = df["Tonaj"].min(), df["Tonaj"].max()
    if max_tonaj > min_tonaj:
        df["Normalize_Tonaj"] = 1.0 + ((df["Tonaj"] - min_tonaj) / (max_tonaj - min_tonaj)) * (MAKSIMUM_CARPAN_TONAJ - 1.0)
    else:
        df["Normalize_Tonaj"] = 1.0

    if "Metrekare (m2)" not in df.columns:
        if "Metrekare" in df.columns:
            df["Metrekare (m2)"] = df["Metrekare"].apply(metrekare_ayikla).replace(0, 1.0)
        else:
            df["Metrekare (m2)"] = 1.0
    else: 
        df["Metrekare (m2)"] = df["Metrekare (m2)"].apply(metrekare_ayikla).replace(0, 1.0)

    makasli_mask = df["Ürün Çeşidi"].str.lower().str.contains("makaslı", na=False)
    min_m2, max_m2 = (df.loc[makasli_mask, "Metrekare (m2)"].min(), df.loc[makasli_mask, "Metrekare (m2)"].max()) if makasli_mask.any() else (1.0, 1.0)

    def m2_normalize_hesapla(row):
        urun = str(row["Ürün Çeşidi"]).lower()
        if "makaslı" in urun and max_m2 > min_m2:
            return 1.0 + ((row["Metrekare (m2)"] - min_m2) / (max_m2 - min_m2)) * (MAKSIMUM_CARPAN_M2 - 1.0)
        return 1.0 

    df["Normalize_Metrekare"] = df.apply(m2_normalize_hesapla, axis=1)
    
    if "Teknik Puan" not in df.columns: 
        df["Normalize_Teknik"] = 1.0 
    else: 
        df["Teknik Puan"] = pd.to_numeric(df["Teknik Puan"], errors='coerce').fillna(1.0)
        df["Normalize_Teknik"] = 1.0 + ((df["Teknik Puan"] - 1.0) / 9.0) * (MAKSIMUM_CARPAN_TEKNIK - 1.0)

    df["Sipariş Başlangıç Tarihi"] = pd.to_datetime(df["Sipariş Başlangıç"], dayfirst=True, errors='coerce')
    df["Sipariş Çıkış Tarihi"] = pd.to_datetime(df["Sipariş Çıkış(Boya Hariç)"], dayfirst=True, errors='coerce')
    df["Teslim Süresi (Gün)"] = (df["Sipariş Çıkış Tarihi"] - df["Sipariş Başlangıç Tarihi"]).dt.days

    return df

try:
    df = veri_isle(yuklenen_dosya)
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Gelişmiş Filtreleme Paneli")
    
    secilen_tezgah = st.sidebar.selectbox("Tezgah Seçin", ["Tümü"] + list(df["Tezgah"].dropna().unique()))
    
    tum_operatorler = set()
    for ops in df["Operatörler"].dropna().astype(str):
        for op in ops.split(','):
            temiz_op = op.strip()
            if temiz_op:
                tum_operatorler.add(temiz_op)
                
    secilen_operator = st.sidebar.selectbox("Operatör Seçin", ["Tümü"] + sorted(list(tum_operatorler)))
    
    df_filtred = df.copy()
    if secilen_tezgah != "Tümü":
        df_filtred = df_filtred[df_filtred["Tezgah"] == secilen_tezgah]
        
    if secilen_operator != "Tümü":
        df_filtred = df_filtred[df_filtred["Operatörler"].fillna("").str.contains(secilen_operator, na=False)]

    tab1, tab2, tab3 = st.tabs(["📊 Ürün & Yük Analizi", "👷 Operatör Performans", "📈 Histogram Dağılımı"])
    
    with tab1:
        st.subheader("Ürün Çeşidi Bazında Üretim Özeti")
        if not df_filtred.empty:
            grup_ozet = df_filtred.groupby(["Ürün Çeşidi", "Zorluk Katsayısı"]).agg({
                "Üretim Adedi": ["sum", "mean"],
                "Teslim Süresi (Gün)": "mean",
                "Sipariş No": "count" if "Sipariş No" in df_filtred.columns else lambda x: len(x)
            }).reset_index()
            grup_ozet.columns = ["Ürün Çeşidi", "Katsayı", "Toplam Üretim", "Ortalama Üretim", "Ortalama Teslim Süresi (Gün)", "İşlenen Sipariş Sayısı"]
            st.dataframe(grup_ozet, use_container_width=True)
        else:
            st.info("Seçilen filtrelere uygun veri bulunamadı.")

    with tab2:
        st.subheader("Normalize Edilmiş Operatör Performans Puanları")
        if not df_filtred.empty:
            df_op = df_filtred.copy()
            df_op['Operatörler'] = df_op['Operatörler'].fillna('').astype(str)
            df_op['Kişi Sayısı'] = df_op['Operatörler'].str.count(',') + 1
            df_op['Operatörler'] = df_op['Operatörler'].str.split(',')
            df_op = df_op.explode('Operatörler')
            df_op['Operatörler'] = df_op['Operatörler'].str.strip()
            df_op = df_op[df_op['Operatörler'] != '']
            
            df_op['Toplam Puan'] = (df_op['Üretim Adedi'] * df_op['Zorluk Katsayısı'] * df_op['Normalize_Tonaj'] * df_op['Çelik Çarpanı'] * df_op['Normalize_Metrekare'] * df_op['Normalize_Teknik'])
            df_op['Kişi Başı Puan'] = df_op['Toplam Puan'] / df_op['Kişi Sayısı']
            
            operator_ozet = df_op.groupby("Operatörler").agg({"Kişi Başı Puan": "sum", "Üretim Adedi": "sum"}).reset_index()
            operator_ozet["Kişi Başı Puan"] = round(operator_ozet["Kişi Başı Puan"], 1)
            operator_ozet.rename(columns={"Üretim Adedi": "Toplam Adet"}, inplace=True)
            st.dataframe(operator_ozet.sort_values(by="Kişi Başı Puan", ascending=False), use_container_width=True)
        else:
            st.info("Seçilen filtrelere uygun veri bulunamadı.")

    with tab3:
        st.subheader("Sipariş Teslim Süreleri Dağılımı (Histogram)")
        if not df_filtred.empty and not df_filtred["Teslim Süresi (Gün)"].dropna().empty:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.hist(df_filtred["Teslim Süresi (Gün)"].dropna(), bins=8, color='steelblue', edgecolor='black', alpha=0.8)
            ax.set_title("Seçilen Filtrelere Göre Teslim Süreleri Dağılımı")
            ax.set_xlabel("Gün")
            ax.set_ylabel("Frekans")
            st.pyplot(fig)
        else:
            st.info("Bu filtre kombinasyonu için çizilebilecek yeterli tarih verisi bulunamadı.")

except ValueError as ve:
    st.warning(f"⚠️ Dosya Yükleme Hatası: {ve}")
except Exception as e:
    st.error(f"Bir hata oluştu: {e}")