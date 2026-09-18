import streamlit as st
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date, timedelta
import json

# ==========================================
# INIZIALIZZAZIONE FIREBASE (LOCALE / CLOUD)
# ==========================================
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            cred_dict = dict(st.secrets["firebase"])
            cred = credentials.Certificate(cred_dict)
        elif "firebase_json" in st.secrets:
            cred_dict = json.loads(st.secrets["firebase_json"])
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate("firebase_key.json")
            
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Errore di connessione a Firebase: Assicurati che i Secrets o il file 'firebase_key.json' siano configurati correttamente. Dettagli: {e}")

db = firestore.client()

# Configurazione della pagina
st.set_page_config(page_title="Gestionale Progetti Cloud", page_icon="📋", layout="wide")

# ==========================================
# STILE GRAFICO ISPIRATO A EUTHRIVE
# ==========================================
st.markdown("""
<style>
    .stApp {
        background-color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #0f172a;
        font-weight: 700;
    }
    .stButton>button {
        background-color: #0d9488;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.4rem 0.8rem;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        background-color: #0f766e;
        color: #ffffff;
    }
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# GESTIONE SESSIONE & STATI
# ==========================================
if "utente_loggato" not in st.session_state:
    st.session_state.utente_loggato = None

if "board_attiva_id" not in st.session_state:
    st.session_state.board_attiva_id = None

if "board_attiva_nome" not in st.session_state:
    st.session_state.board_attiva_nome = None

oggi_str = date.today().strftime("%Y-%m-%d")
if "data_ultima_notifica" not in st.session_state:
    st.session_state.data_ultima_notifica = None

# ==========================================
# FUNZIONE NOTIFICHE BROWSER (JS)
# ==========================================
def attiva_notifiche_browser(lista_task_in_preavviso):
    global oggi_str
    if st.session_state.data_ultima_notifica == oggi_str or not lista_task_in_preavviso:
        return

    notifiche_json = ""
    for t in lista_task_in_preavviso:
        titolo = t['titolo'].replace('"', "'")
        progetto = t['progetto_nome'].replace('"', "'")
        scadenza = t['scadenza']
        notifiche_json += f"{{ title: '⚠️ Promemoria Task', body: 'Progetto: {progetto}\\nTask: {titolo}\\nScadenza: {scadenza}' }},"

    js_code = f"""
    <script>
    function inviaNotifiche() {{
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {{
            mostraPopup();
        }} else if (Notification.permission !== "denied") {{
            Notification.requestPermission().then(function (permission) {{
                if (permission === "granted") {{ mostraPopup(); }}
            }});
        }}
    }}
    function mostraPopup() {{
        const taskDaNotificare = [{notifiche_json}];
        taskDaNotificare.slice(0, 3).forEach(function(item, index) {{
            setTimeout(function() {{
                new Notification(item.title, {{
                    body: item.body,
                    icon: "https://cdn-icons-png.flaticon.com/512/906/906334.png"
                }});
            }}, index * 1000);
        }});
    }}
    inviaNotifiche();
    </script>
    """
    components.html(js_code, height=0, width=0)
    st.session_state.data_ultima_notifica = oggi_str

# ==========================================
# MODALE (POP-UP) PER MODIFICA TASK
# ==========================================
@st.dialog("⚙️ Gestisci Task")
def modal_modifica_task(t_id, t_data, prog_id):
    st.subheader(f"Modifica: {t_data.get('titolo')}")
    
    with st.form(f"form_mod_popup_{t_id}"):
        nuovo_titolo = st.text_input("Titolo Task", value=t_data.get('titolo', ''))
        nuove_note = st.text_area("Note / Descrizione", value=t_data.get('note_task', ''))
        
        sez_docs = db.collection("sezioni_appunti").where("id_progetto", "==", prog_id).stream()
        opzioni_sezioni = ["Nessuna"] + [s.to_dict()['nome'] for s in sez_docs]
        sezione_attuale = t_data.get('sezione_nome', 'Nessuna')
        idx_sez = opzioni_sezioni.index(sezione_attuale) if sezione_attuale in opzioni_sezioni else 0
        
        nuova_sezione = st.selectbox("Collega a Sezione Appunti", opzioni_sezioni, index=idx_sez)
        nuovo_assegnatario = st.text_input("Assegnato a", value=t_data.get('assegnatario', ''))
        
        scad_str = t_data.get('scadenza', '')
        ha_scad = st.checkbox("Imposta Scadenza", value=bool(scad_str))
        nuova_scad = st.date_input("Data Scadenza", value=datetime.strptime(scad_str, "%Y-%m-%d").date() if scad_str else date.today())
        
        stato = t_data.get("stato", "Normale")
        nuovo_stato = st.selectbox("Stato Task", ["Normale", "Bloccata"], index=0 if stato != "Bloccata" else 1)
        completata = t_data.get("completata", 0)
        nuova_completata = st.selectbox("Completata?", [0, 1], index=completata, format_func=lambda x: "Sì" if x==1 else "No")

        col_salva, col_elimina = st.columns(2)
        with col_salva:
            btn_salva = st.form_submit_button("Salva Modifiche")
        with col_elimina:
            btn_elimina = st.form_submit_button("Elimina Task", type="primary")

        if btn_salva:
            db.collection("task").document(t_id).update({
                "titolo": nuovo_titolo,
                "note_task": nuove_note,
                "sezione_nome": nuova_sezione,
                "assegnatario": nuovo_assegnatario,
                "scadenza": nuova_scad.strftime("%Y-%m-%d") if ha_scad else "",
                "stato": nuovo_stato,
                "completata": nuova_completata
            })
            st.success("Task aggiornata con successo!")
            st.rerun()
            
        if btn_elimina:
            db.collection("task").document(t_id).delete()
            st.success("Task eliminata!")
            st.rerun()

# ==========================================
# LOGIN / REGISTRAZIONE
# ==========================================
def schermata_login():
    st.title("🔐 Accesso al Gestionale Cloud")
    tab_accedi, tab_registrati = st.tabs(["🔑 Accedi", "📝 Registrati"])
    
    with tab_accedi:
        with st.form("form_login"):
            email_login = st.text_input("Email", key="log_email")
            password_login = st.text_input("Password", type="password", key="log_pass")
            btn_entra = st.form_submit_button("Accedi")
            
            if btn_entra:
                if not email_login or not password_login:
                    st.error("Inserisci email e password.")
                else:
                    email_clean = email_login.strip().lower()
                    utenti_ref = db.collection("utenti").where("email", "==", email_clean).where("password", "==", password_login).stream()
                    if list(utenti_ref):
                        st.session_state.utente_loggato = email_clean
                        st.success("Accesso effettuato!")
                        st.rerun()
                    else:
                        st.error("Email o password errati.")

    with tab_registrati:
        with st.form("form_registrazione"):
            email_reg = st.text_input("Nuova Email", key="reg_email")
            password_reg = st.text_input("Nuova Password", type="password", key="reg_pass")
            password_conferma = st.text_input("Conferma Password", type="password", key="reg_conf")
            btn_reg = st.form_submit_button("Registrati")
            
            if btn_reg:
                if not email_reg or not password_reg:
                    st.error("Compila tutti i campi.")
                elif password_reg != password_conferma:
                    st.error("Le password non coincidono.")
                else:
                    email_clean = email_reg.strip().lower()
                    if list(db.collection("utenti").where("email", "==", email_clean).stream()):
                        st.error("Email già registrata.")
                    else:
                        db.collection("utenti").add({
                            "email": email_clean,
                            "password": password_reg,
                            "data_registrazione": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        st.success("Registrazione completata! Effettua l'accesso.")

# ==========================================
# SELETTORE / GESTIONE BOARD
# ==========================================
def schermata_selezione_board():
    st.title(f"👋 Benvenuto, {st.session_state.utente_loggato}")
    st.markdown("Seleziona una board o creane una nuova.")

    with st.expander("➕ Crea una Nuova Board"):
        with st.form("form_nuova_board"):
            nome_board = st.text_input("Nome Board")
            membri_extra = st.text_input("Membri aggiuntivi (email separate da virgola)")
            btn_crea_b = st.form_submit_button("Crea Board")

            if btn_crea_b and nome_board:
                lista_membri = [st.session_state.utente_loggato]
                if membri_extra:
                    lista_membri.extend([m.strip().lower() for m in membri_extra.split(",") if m.strip()])
                db.collection("board").add({
                    "nome": nome_board,
                    "proprietario": st.session_state.utente_loggato,
                    "membri": list(set(lista_membri))
                })
                st.success("Board creata!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Le tue Board Disponibili")

    board_docs = db.collection("board").stream()
    mie_board = [ {"id": b.id, **b.to_dict()} for b in board_docs if st.session_state.utente_loggato in [m.lower() for m in b.to_dict().get("membri", [])] ]

    if not mie_board:
        st.info("Nessuna board disponibile.")
    else:
        for b in mie_board:
            b_id = b['id']
            proprietario = b.get('proprietario', '')
            is_proprietario = (proprietario == st.session_state.utente_loggato)

            with st.container(border=True):
                col_b1, col_b2 = st.columns([3, 1])
                with col_b1:
                    st.markdown(f"### 📌 {b['nome']}")
                    st.caption(f"Proprietario: {proprietario} | Membri: {', '.join(b.get('membri', []))}")
                with col_b2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("Entra", key=f"entra_b_{b_id}"):
                        st.session_state.board_attiva_id = b_id
                        st.session_state.board_attiva_nome = b['nome']
                        st.rerun()

                if is_proprietario:
                    with st.expander(f"⚙️ Gestione Accessi & Eliminazione ({b['nome']})"):
                        membri_attuali = b.get("membri", [])
                        with st.form(f"form_invito_{b_id}"):
                            nuova_email = st.text_input("Aggiungi utente", key=f"email_{b_id}")
                            if st.form_submit_button("Aggiungi") and nuova_email:
                                e_pulita = nuova_email.strip().lower()
                                if e_pulita not in membri_attuali:
                                    membri_attuali.append(e_pulita)
                                    db.collection("board").document(b_id).update({"membri": membri_attuali})
                                    st.rerun()
                        
                        if st.button("🗑️ Elimina Intera Board", key=f"del_board_{b_id}", type="primary"):
                            db.collection("board").document(b_id).delete()
                            for p in db.collection("progetti").where("id_board", "==", b_id).stream():
                                db.collection("progetti").document(p.id).delete()
                            st.rerun()

    if st.button("🚪 Logout"):
        st.session_state.utente_loggato = None
        st.session_state.board_attiva_id = None
        st.session_state.board_attiva_nome = None
        st.rerun()

# ==========================================
# INTERFACCIA PRINCIPALE
# ==========================================
def schermata_principale():
    st.sidebar.title("Workspace")
    st.sidebar.markdown(f"📌 Board: **{st.session_state.board_attiva_nome}**")
    st.sidebar.markdown(f"👤 Utente: **{st.session_state.utente_loggato}**")
    
    if st.sidebar.button("🔄 Cambia Board"):
        st.session_state.board_attiva_id = None
        st.session_state.board_attiva_nome = None
        st.rerun()

    st.sidebar.markdown("---")
    menu = st.sidebar.radio("Vista:", ["📋 Board Progetti (Kanban)", "⏳ Board Scadenze", "📅 Calendario", "📁 Progetti"])
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.utente_loggato = None
        st.session_state.board_attiva_id = None
        st.session_state.board_attiva_nome = None
        st.rerun()

    id_board = st.session_state.board_attiva_id

    # --- 1. KANBAN PROGETTI ---
    if menu == "📋 Board Progetti (Kanban)":
        st.header(f"📋 Board Progetti Kanban - {st.session_state.board_attiva_nome}")

        nascondi_completate = st.checkbox("Nascondi task completate", value=False)

        progetti_docs = db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()
        progetti_lista = [{"id": p.id, **p.to_dict()} for p in progetti_docs]
        progetti_lista = sorted(progetti_lista, key=lambda x: x.get('ordine', 0))

        if not progetti_lista:
            st.info("Nessun progetto trovato. Creane uno nella scheda 'Progetti'.")
        else:
            oggi = date.today()

            # INIZIO HACK CSS: Forza rigidamente larghezza e comportamento a scorrimento
            st.markdown("""
            <style>
                /* Contenitore principale (riga orizzontale) */
                div[data-testid="stHorizontalBlock"] {
                    flex-wrap: nowrap !important;
                    overflow-x: auto !important;
                    padding-bottom: 20px;
                    align-items: flex-start !important;
                }
                
                /* Colonne Kanban principali (IGNORA le percentuali di Streamlit) */
                div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                    min-width: 360px !important; /* Forza larghezza minima */
                    max-width: 360px !important; /* Forza larghezza massima */
                    width: 360px !important;     /* Sovrascrive le percentuali inline! */
                    flex: 0 0 360px !important;  /* Blocca la crescita/riduzione del flexbox */
                    background-color: #f1f5f9;
                    padding: 15px;
                    border-radius: 10px;
                    border: 1px solid #e2e8f0;
                }

                /* RESET per le sotto-colonne all'interno delle card (es. bottoni di spostamento) */
                div[data-testid="column"] div[data-testid="stHorizontalBlock"] {
                    flex-wrap: wrap !important;
                    overflow-x: visible !important;
                    padding-bottom: 0 !important;
                }
                div[data-testid="column"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                    min-width: 0 !important;
                    max-width: none !important;
                    width: auto !important;
                    flex: 1 1 0% !important;
                    background-color: transparent !important;
                    padding: 0 !important;
                    border: none !important;
                }
            </style>
            """, unsafe_allow_html=True)

            colonne = st.columns(len(progetti_lista))

            for idx, prog in enumerate(progetti_lista):
                prog_id = prog['id']
                
                with colonne[idx]:
                    st.markdown(f"<h3 style='margin-top:0;'>📁 {prog['nome']}</h3>", unsafe_allow_html=True)
                    if prog.get('descrizione'):
                        st.caption(prog['descrizione'])
                        
                    c_l, c_r = st.columns(2)
                    with c_l:
                        if idx > 0 and st.button("◀️ Sposta", key=f"p_left_{prog_id}", use_container_width=True):
                            prev_p = progetti_lista[idx - 1]
                            db.collection("progetti").document(prog_id).update({"ordine": prev_p.get('ordine', idx)})
                            db.collection("progetti").document(prev_p['id']).update({"ordine": prog.get('ordine', idx + 1)})
                            st.rerun()
                    with c_r:
                        if idx < len(progetti_lista) - 1 and st.button("Sposta ▶️", key=f"p_right_{prog_id}", use_container_width=True):
                            next_p = progetti_lista[idx + 1]
                            db.collection("progetti").document(prog_id).update({"ordine": next_p.get('ordine', idx + 2)})
                            db.collection("progetti").document(next_p['id']).update({"ordine": prog.get('ordine', idx + 1)})
                            st.rerun()
                    
                    st.markdown("---")

                    tasks_docs = db.collection("task").where("id_progetto", "==", prog_id).stream()
                    
                    for t_doc in tasks_docs:
                        t_data = t_doc.to_dict()
                        t_id = t_doc.id
                        completata = t_data.get("completata", 0)
                        stato = t_data.get("stato", "Normale")

                        if nascondi_completate and completata == 1:
                            continue

                        scad_str = t_data.get("scadenza", "")
                        giorni_diff = 999
                        if scad_str:
                            try:
                                d_scad = datetime.strptime(scad_str, "%Y-%m-%d").date()
                                giorni_diff = (d_scad - oggi).days
                            except:
                                pass

                        bordo_colore = "#cbd5e1" 
                        if completata == 1:
                            bordo_colore = "#10b981" # Verde
                        elif stato == "Bloccata" or giorni_diff < 0:
                            bordo_colore = "#ef4444" # Rosso
                        elif 0 <= giorni_diff <= 7:
                            bordo_colore = "#f59e0b" # Arancione

                        sezione_collegata = t_data.get('sezione_nome', 'Nessuna')
                        badge_sezione = f"🔗 {sezione_collegata}" if sezione_collegata and sezione_collegata != "Nessuna" else ""

                        card_html = f"""
                        <div style="border: 2px solid {bordo_colore}; border-radius: 8px; padding: 12px; background-color: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,0.05); margin-bottom: 5px;">
                            <strong style="color: #0f172a; font-size: 1.05em;">{t_data.get('titolo')}</strong><br>
                            <div style="margin-top: 6px; font-size: 0.85em; color: #475569;">👤 {t_data.get('assegnatario', 'N/D')} | 📅 {scad_str or 'No scad'}</div>
                            <div style="margin-top: 6px;"><span style="font-size: 0.8em; color: #334155; background-color: #f1f5f9; padding: 3px 8px; border-radius: 4px;">{badge_sezione} | Stato: {stato}</span></div>
                        </div>
                        """
                        st.markdown(card_html, unsafe_allow_html=True)
                        
                        if t_data.get('note_task'):
                            st.info(f"📝 {t_data.get('note_task')}")

                        if st.button("⚙️ Modifica / Apri", key=f"btn_mod_{t_id}", use_container_width=True):
                            modal_modifica_task(t_id, t_data, prog_id)
                        
                        st.markdown("<br>", unsafe_allow_html=True)

                    with st.expander("➕ Nuova Task"):
                        sez_docs = db.collection("sezioni_appunti").where("id_progetto", "==", prog_id).stream()
                        opzioni_sezioni = ["Nessuna"] + [s.to_dict()['nome'] for s in sez_docs]

                        with st.form(f"form_task_{prog_id}"):
                            t_titolo = st.text_input("Titolo Task")
                            t_nota = st.text_area("Note Task")
                            t_sez = st.selectbox("Sezione Appunti", opzioni_sezioni)
                            t_assegnatario = st.text_input("Assegnato a", value=st.session_state.utente_loggato)
                            t_scad = st.date_input("Scadenza")
                            
                            if st.form_submit_button("Crea Task"):
                                db.collection("task").add({
                                    "id_progetto": prog_id,
                                    "titolo": t_titolo,
                                    "note_task": t_nota,
                                    "sezione_nome": t_sez,
                                    "assegnatario": t_assegnatario,
                                    "scadenza": t_scad.strftime("%Y-%m-%d"),
                                    "stato": "Normale",
                                    "completata": 0,
                                    "preavviso": 3
                                })
                                st.success("Task creata!")
                                st.rerun()

    # --- 2. BOARD SCADENZE ---
    elif menu == "⏳ Board Scadenze":
        st.header("⏳ Board Scadenze")
        progetti_dict = {doc.id: doc.to_dict().get('nome', 'Progetto') for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
        
        tasks_lista = []
        if progetti_dict:
            oggi = date.today()
            for t in db.collection("task").stream():
                t_data = t.to_dict()
                if t_data.get("id_progetto") in progetti_dict:
                    t_item = {"id": t.id, **t_data, "progetto_nome": progetti_dict[t_data.get("id_progetto")]}
                    scad_str = t_data.get("scadenza", "")
                    if not scad_str:
                        t_item["cat"] = "no_scad"
                    else:
                        diff = (datetime.strptime(scad_str, "%Y-%m-%d").date() - oggi).days
                        if diff <= 0: t_item["cat"] = "oggi"
                        elif diff <= 7: t_item["cat"] = "settimana"
                        else: t_item["cat"] = "prossime"
                    tasks_lista.append(t_item)

        c1, c2, c3, c4 = st.columns(4)
        cats = [("🚨 Scadute / Oggi", "oggi", c1), ("⚠️ Questa Settimana", "settimana", c2), ("📅 Prossime", "prossime", c3), ("📌 No Scadenza", "no_scad", c4)]
        
        for titolo_col, cat_key, col_obj in cats:
            with col_obj:
                st.markdown(f"### {titolo_col}")
                st.markdown("---")
                filtrate = [t for t in tasks_lista if t.get("cat") == cat_key]
                if not filtrate:
                    st.info("Nessuna task.")
                else:
                    for t in filtrate:
                        with st.container(border=True):
                            st.markdown(f"**{t['titolo']}**")
                            st.caption(f"📁 {t['progetto_nome']} | 👤 {t.get('assegnatario')}")
                            st.caption(f"📅 {t.get('scadenza', 'Nessuna')}")

    # --- 3. CALENDARIO ---
    elif menu == "📅 Calendario":
        st.header("📅 Calendario Scadenze")
        try:
            from streamlit_calendar import calendar
        except ImportError:
            calendar = None

        if calendar:
            progetti_dict = {doc.id: doc.to_dict().get('nome', 'Progetto') for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
            events = []
            if progetti_dict:
                for t in db.collection("task").stream():
                    t_data = t.to_dict()
                    if t_data.get("id_progetto") in progetti_dict and t_data.get("scadenza"):
                        colore = "#10b981" if t_data.get("completata") == 1 else "#0d9488"
                        events.append({
                            "title": f"[{progetti_dict[t_data['id_progetto']]}] {t_data['titolo']}",
                            "start": t_data['scadenza'],
                            "end": t_data['scadenza'],
                            "backgroundColor": colore
                        })
            calendar(events=events, options={"initialView": "dayGridMonth"}, key="cal")

    # --- 4. PROGETTI E SEZIONI ---
    elif menu == "📁 Progetti":
        st.header(f"📁 Gestione Progetti - {st.session_state.board_attiva_nome}")
        
        with st.expander("➕ Nuovo Progetto"):
            with st.form("form_nuovo_p"):
                nome_p = st.text_input("Nome Progetto")
                desc_p = st.text_area("Descrizione")
                if st.form_submit_button("Crea") and nome_p:
                    esistenti = list(db.collection("progetti").where("id_board", "==", id_board).stream())
                    db.collection("progetti").add({
                        "id_board": id_board, "nome": nome_p, "descrizione": desc_p,
                        "proprietario": st.session_state.utente_loggato, "archiviato": 0, "ordine": len(esistenti) + 1
                    })
                    st.rerun()

        st.markdown("---")
        progs = {doc.to_dict()['nome']: doc.id for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
        if progs:
            scelta = st.selectbox("Seleziona Progetto", list(progs.keys()))
            p_id = progs[scelta]

            if st.button("🗑️ Elimina Progetto", type="primary"):
                db.collection("progetti").document(p_id).delete()
                for s in db.collection("sezioni_appunti").where("id_progetto", "==", p_id).stream(): db.collection("sezioni_appunti").document(s.id).delete()
                for t in db.collection("task").where("id_progetto", "==", p_id).stream(): db.collection("task").document(t.id).delete()
                st.rerun()

            st.markdown("---")
            with st.expander("➕ Nuova Sezione Appunti"):
                with st.form("form_nota"):
                    n_titolo = st.text_input("Titolo Sezione")
                    n_testo = st.text_area("Contenuto")
                    if st.form_submit_button("Salva") and n_titolo:
                        sezs = list(db.collection("sezioni_appunti").where("id_progetto", "==", p_id).stream())
                        db.collection("sezioni_appunti").add({
                            "id_progetto": p_id, "nome": n_titolo, "contenuto": n_testo,
                            "ordine": len(sezs) + 1, "autore": st.session_state.utente_loggato
                        })
                        st.rerun()

            sezioni = sorted([{"id": s.id, **s.to_dict()} for s in db.collection("sezioni_appunti").where("id_progetto", "==", p_id).stream()], key=lambda x: x.get('ordine', 0))
            
            for i, sez in enumerate(sezioni):
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"### 📌 {sez['nome']}")
                        st.write(sez['contenuto'])
                    with c2:
                        if i > 0:
                            if st.button("⬆️", key=f"sup_{sez['id']}"):
                                prev_s = sezioni[i-1]
                                ordine_attuale = sez.get('ordine', i)
                                ordine_precedente = prev_s.get('ordine', i-1)
                                db.collection("sezioni_appunti").document(sez['id']).update({"ordine": ordine_precedente})
                                db.collection("sezioni_appunti").document(prev_s['id']).update({"ordine": ordine_attuale})
                                st.rerun()
                                
                        if i < len(sezioni) - 1:
                            if st.button("⬇️", key=f"sdown_{sez['id']}"):
                                next_s = sezioni[i+1]
                                ordine_attuale = sez.get('ordine', i)
                                ordine_successivo = next_s.get('ordine', i+1)
                                db.collection("sezioni_appunti").document(sez['id']).update({"ordine": ordine_successivo})
                                db.collection("sezioni_appunti").document(next_s['id']).update({"ordine": ordine_attuale})
                                st.rerun()
                                
                        if st.button("🗑️", key=f"sdel_{sez['id']}"):
                            db.collection("sezioni_appunti").document(sez['id']).delete()
                            st.rerun()

# ==========================================
# FLUSSO PRINCIPALE
# ==========================================
if st.session_state.utente_loggato is None:
    schermata_login()
elif st.session_state.board_attiva_id is None:
    schermata_selezione_board()
else:
    schermata_principale()
