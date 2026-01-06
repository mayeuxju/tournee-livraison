import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Tournées 🚚", layout="wide")

st.title("🚚 Optimiseur de Tournées")

# Initialiser les données
if 'livraisons' not in st.session_state:
    st.session_state.livraisons = []

# ===== FORMULAIRE AJOUT =====
st.header("➕ Ajouter une livraison")

with st.form("ajout_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        nom = st.text_input("Client")
        adresse = st.text_input("Adresse")
    
    with col2:
        heure = st.time_input("Heure de livraison", value=datetime.strptime("09:00", "%H:%M").time())
    
    if st.form_submit_button("✅ Ajouter", type="primary"):
        if nom and adresse:
            st.session_state.livraisons.append({
                'Client': nom,
                'Adresse': adresse,
                'Heure': heure.strftime("%H:%M")
            })
            st.success(f"✅ {nom} ajouté !")
            st.rerun()
        else:
            st.error("⚠️ Remplissez tous les champs")

# ===== AFFICHAGE =====
st.divider()
st.header(f"📦 Livraisons ({len(st.session_state.livraisons)})")

if st.session_state.livraisons:
    # Trier par heure
    livraisons_triees = sorted(st.session_state.livraisons, key=lambda x: x['Heure'])
    
    # Afficher le tableau
    df = pd.DataFrame(livraisons_triees)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Boutons d'action
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        if st.button("🗑️ Tout effacer"):
            st.session_state.livraisons = []
            st.rerun()
    
    with col_btn2:
        # Export CSV
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv,
            file_name="tournee.csv",
            mime="text/csv"
        )
    
    with col_btn3:
        # Export Google Maps (sans géocodage)
        adresses = " / ".join([l['Adresse'] for l in livraisons_triees])
        google_url = f"https://www.google.com/maps/dir/{adresses.replace(' ', '+')}"
        st.link_button("🗺️ Google Maps", google_url)
    
    # ===== TOURNÉE OPTIMISÉE =====
    st.divider()
    st.header("🚀 Tournée optimisée (par horaire)")
    
    for i, livraison in enumerate(livraisons_triees, 1):
        st.markdown(f"### {i}. {livraison['Client']}")
        st.caption(f"📍 {livraison['Adresse']}")
        st.caption(f"🕐 {livraison['Heure']}")
        if i < len(livraisons_triees):
            st.markdown("↓")
    
    st.success(f"✅ {len(livraisons_triees)} livraisons planifiées")
    
else:
    st.info("👆 Ajoutez votre première livraison")

# Footer
st.divider()
st.caption("💡 Conseil : Ajoutez d'abord votre point de départ")
st.caption("🔄 Version simplifiée - Fonctionne sur tous les mobiles")
