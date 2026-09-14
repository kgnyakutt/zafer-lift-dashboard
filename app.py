elif yz_departman == "🚀 Makine Sevk Süresi (Kaynak + Elektrik)":
        if not df_k.empty and not df_e.empty:
            st.info("💡 **Bilgi:** Bu tahminleme modeli, önce Kaynak/İmalat yapay zekasını çalıştırır, ardından Elektrik montaj süresini hesaplar. Elektrik saatini mesai gününe (8 saat) çevirip toplam sevke çıkma süresini verir.")
            
            # İki modeli de aynı anda eğitiyoruz
            X_k = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Normalize_Teknik", "Çelik Çarpanı", "Tabla_Carpani", "Kilitleme_Carpani", "Uzunluk_Carpani", "Kişi Sayısı"]
            rf_net_k, _, sc_k, _, _ = yapay_zeka_egit(df_k, X_k, birim="gun")
            
            X_e = ["Zorluk Katsayısı", "Normalize_Kapasite", "Normalize_Ebat", "Uzunluk_Carpani", "Normalize_Durak", "Kilitleme_Carpani", "Sıfırlama_Carpani", "Tabla Kapısı_Carpani", "Yavaşlama_Carpani", "Buton Tipi_Carpani", "İkaz Lambaları_Carpani", "PLC_Carpani", "PLC_Model_Carpani", "Kişi Sayısı"]
            rf_net_e, _, sc_e, _, _ = yapay_zeka_egit(df_e, X_e, birim="saat")
            
            if rf_net_k and rf_net_e:
                st.markdown("##### ⚙️ Makine Özellikleri ve Atölye Ekipleri")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("**1. Ortak Özellikler**")
                    in_s_urun = st.selectbox("Model Seçimi", sorted(df_k["Model"].unique()), key="s_urun")
                    in_s_kapasite = st.number_input("Kapasite (Ton)", value=1.0, key="s_kap")
                    in_s_m2 = st.number_input("Platform Ebatı (m2)", value=5.0, key="s_m2")
                    in_s_tabla = st.selectbox("Tabla Kapısı Var mı?", [0, 1], key="s_tab")
                    in_s_kilit = st.selectbox("Kilitleme Var mı?", [0, 1], key="s_kil")
                
                with col2:
                    st.markdown("**2. Kaynak Detayları**")
                    in_s_teknik = st.slider("Teknik Zorluk Puanı", 1.0, 10.0, 1.0, key="s_tek")
                    in_s_celik = st.selectbox("Çelik Durumu Nasıl?", [0, 1], key="s_cel")
                    in_s_kisi_k = st.number_input("Kaynak Ekibi Kişi Sayısı", min_value=1, value=2, key="s_kisi_k")
                
                with col3:
                    st.markdown("**3. Elektrik Detayları**")
                    in_s_durak = st.number_input("Durak Sayısı", min_value=1, value=3, key="s_dur")
                    in_s_plc = st.selectbox("PLC Kullanılacak mı?", [0, 1], key="s_plc")
                    in_s_model = st.selectbox("PLC Markası", ["Gemo", "Delta", "Omron", "Schneider", "Siemens"], key="s_mod")
                    in_s_kisi_e = st.number_input("Elektrik Ekibi Kişi Sayısı", min_value=1, value=1, key="s_kisi_e")
                
                if st.button("🚀 Toplam Sevk Süresini Hesapla", use_container_width=True):
                    # Kaynak Çarpanları
                    t_carp = 1.1 if in_s_tabla == 1 else 1.0
                    k_carp = 1.2 if in_s_kilit == 1 else 1.0
                    u_carp = 1.0 
                    
                    # Kaynak Yapay Zeka Tahmini
                    ham_veri_k = np.array([[2.5, 1.2, 1.1, 1.0 + (in_s_teknik/10), in_s_celik+1.0, t_carp, k_carp, u_carp, in_s_kisi_k]]) 
                    tahmin_kaynak_gun = max(rf_net_k.predict(sc_k.transform(ham_veri_k))[0], 1.0)
                    
                    # Elektrik Yapay Zeka Tahmini
                    p_carp = 1.2 if in_s_plc == 1 else 1.0
                    m_carp = 1.1 if in_s_plc == 1 else 1.0
                    ham_veri_e = np.array([[1.5, 1.2, 1.2, 1.0, 1.1, k_carp, 1.0, t_carp, 1.0, 1.0, 1.0, p_carp, m_carp, in_s_kisi_e]])
                    tahmin_elektrik_saat = max(rf_net_e.predict(sc_e.transform(ham_veri_e))[0], 0.5)
                    
                    # Saat -> Gün dönüşümü (Ortalama bir gün 8 saat mesai sayılmıştır)
                    elektrik_gun_karsiligi = tahmin_elektrik_saat / 8.0
                    toplam_sevk_gun = tahmin_kaynak_gun + elektrik_gun_karsiligi
                    
                    st.success("🎯 **Tahmin Tamamlandı!** Makinenin üretime girip elektrik testlerinin biterek sevke hazır hale gelmesi için gereken süre:")
                    
                    r_col1, r_col2, r_col3 = st.columns(3)
                    with r_col1:
                        st.info(f"🛠️ **Kaynak İmalatı:**\n\n### {tahmin_kaynak_gun:.1f} Gün")
                    with r_col2:
                        st.info(f"⚡ **Elektrik İşlemi:**\n\n### {tahmin_elektrik_saat:.1f} Saat\n*(~{elektrik_gun_karsiligi:.1f} Gün)*")
                    with r_col3:
                        st.error(f"🚀 **TOPLAM SEVK SÜRESİ:**\n\n### {toplam_sevk_gun:.1f} Gün")
                        
            else:
                st.warning("Yapay Zeka modellerini eğitmek için yeterli veri yok.")
        else:
            st.warning("Bu tahmini yapmak için hem Kaynak hem de Elektrik verilerinin Google Sheets'te dolu olması gerekmektedir.")
