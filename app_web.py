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
                if (permission === "granted") {{ mostraPopup(); }
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

    # --- 1. KANBAN PROGETTI (Con ordinamento colonne e task colorate/modificabili) ---
    if menu == "📋 Board Progetti (Kanban)":
        st.header(f"📋 Board Progetti Kanban - {st.session_state.board_attiva_nome}")

        # Opzione per nascondere le task completate
        nascondi_completate = st.checkbox("Nascondi task completate", value=False)

        progetti_docs = db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()
        progetti_lista = [{"id": p.id, **p.to_dict()} for p in progetti_docs]
        progetti_lista = sorted(progetti_lista, key=lambda x: x.get('ordine', 0))

        if not progetti_lista:
            st.info("Nessun progetto trovato. Creane uno nella scheda 'Progetti'.")
        else:
            colonne = st.columns(len(progetti_lista))
            oggi = date.today()

            for idx, prog in enumerate(progetti_lista):
                prog_id = prog['id']
                with colonne[idx]:
                    # Intestazione colonna con bottoni per riordinare i progetti a sinistra/destra
                    c_tit, c_ord1, c_ord2 = st.columns([4, 1, 1])
                    with c_tit:
                        st.markdown(f"### 📁 {prog['nome']}")
                    with c_ord1:
                        if idx > 0 and st.button("⬅️", key=f"p_left_{prog_id}"):
                            prev_p = progetti_lista[idx - 1]
                            db.collection("progetti").document(prog_id).update({"ordine": prev_p.get('ordine', idx)})
                            db.collection("progetti").document(prev_p['id']).update({"ordine": prog.get('ordine', idx + 1)})
                            st.rerun()
                    with c_ord2:
                        if idx < len(progetti_lista) - 1 and st.button("➡️", key=f"p_right_{prog_id}"):
                            next_p = progetti_lista[idx + 1]
                            db.collection("progetti").document(prog_id).update({"ordine": next_p.get('ordine', idx + 2)})
                            db.collection("progetti").document(next_p['id']).update({"ordine": prog.get('ordine', idx + 1)})
                            st.rerun()

                    if prog.get('descrizione'):
                        st.caption(prog['descrizione'])
                    st.markdown("---")

                    tasks_docs = db.collection("task").where("id_progetto", "==", prog_id).stream()
                    
                    for t_doc in tasks_docs:
                        t_data = t_doc.to_dict()
                        t_id = t_doc.id
                        completata = t_data.get("completata", 0)
                        stato = t_data.get("stato", "Normale") # Normale, Bloccata, etc.

                        if nascondi_completate and completata == 1:
                            continue

                        # Calcolo Colore Scheda
                        #Verdi completate, arancioni in scadenza questa settimana, rosse bloccate o scadute
                        scad_str = t_data.get("scadenza", "")
                        bordo_colore = "#e0e0e0" # neutro
                        sfondo_colore = "transparent"
                        
                        giorni_diff = 999
                        if scad_str:
                            try:
                                d_scad = datetime.strptime(scad_str, "%Y-%m-%d").date()
                                giorni_diff = (d_scad - oggi).days
                            except:
                                pass

                        if completata == 1:
                            bordo_colore = "#28a745" # Verde
                        elif stato == "Bloccata" or giorni_diff < 0:
                            bordo_colore = "#dc3545" # Rosso
                        elif 0 <= giorni_diff <= 7:
                            bordo_colore = "#ffc107" # Arancione / Giallo settimana

                        with st.container(border=True):
                            st.markdown(f"**{t_data.get('titolo')}**")
                            if t_data.get('sezione_nome') and t_data.get('sezione_nome') != "Nessuna":
                                st.caption(f"🔗 {t_data.get('sezione_nome')}")
                            st.caption(f"👤 {t_data.get('assegnatario', 'N/D')} | 📅 {scad_str or 'No scad'}")
                            if t_data.get('note_task'):
                                st.info(f"📝 {t_data.get('note_task')}")

                            # Expander per modificare la task o cambiarne lo stato
                            with st.expander("⚙️ Modifica Task"):
                                with st.form(f"form_mod_task_{t_id}"):
                                    nuovo_titolo = st.text_input("Titolo", value=t_data.get('titolo', ''))
                                    nuove_note = st.text_area("Note Task", value=t_data.get('note_task', ''))
                                    nuovo_assegnatario = st.text_input("Assegnato a", value=t_data.get('assegnatario', ''))
                                    
                                    ha_scad = st.bool = st.checkbox("Ha scadenza", value=bool(scad_str))
                                    nuova_scad = st.date_input("Data scadenza", value=datetime.strptime(scad_str, "%Y-%m-%d").date() if scad_str else date.today())
                                    
                                    nuovo_stato = st.selectbox("Stato Task", ["Normale", "Bloccata"], index=0 if stato != "Bloccata" else 1)
                                    nuova_completata = st.selectbox("Completata?", [0, 1], index=completata, format_func=lambda x: "Sì" if x==1 else "No")

                                    if st.form_submit_button("Salva Modifiche"):
                                        db.collection("task").document(t_id).update({
                                            "titolo": nuovo_titolo,
                                            "note_task": nuove_note,
                                            "assegnatario": nuovo_assegnatario,
                                            "scadenza": nuova_scad.strftime("%Y-%m-%d") if ha_scad else "",
                                            "stato": nuovo_stato,
                                            "completata": nuova_completata
                                        })
                                        st.success("Aggiornato!")
                                        st.rerun()

                            if st.button("🗑️ Elimina", key=f"del_t_{t_id}"):
                                db.collection("task").document(t_id).delete()
                                st.rerun()

                    # Form Aggiungi Task
                    with st.expander("➕ Aggiungi Task"):
                        sez_docs = db.collection("sezioni_appunti").where("id_progetto", "==", prog_id).stream()
                        opzioni_sezioni = ["Nessuna"] + [s.to_dict()['nome'] for s in sez_docs]

                        with st.form(f"form_task_{prog_id}"):
                            t_titolo = st.text_input("Titolo Task")
                            t_nota = st.text_area("Note / Descrizione Task")
                            t_sez = st.selectbox("Sezione", opzioni_sezioni)
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
                        colore = "#28a745" if t_data.get("completata") == 1 else "#007bff"
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
                        if i > 0 and st.button("⬆️", key=f"sup_{sez['id']}"):
                            prev_s = sezioni[i-1]
                            db.collection("sezioni_appunti").document(sez['id']).update({"ordine": prev_s.get('ordine', i)})
                            db.collection("sezioni_appunti").document(prev_s['id']).update({"ordine": sez.get('ordine', i+1)})
                            st.rerun()
                        if i < len(sezioni)-1 and st.button("⬇️", key=f"sdown_{sez['id']}"):
                            next_s = sezioni[i+1]
                            db.collection("sezioni_appunti").document(sez['id']).update({"ordine": next_s.get('ordine', i+2)})
                            db.collection("sezioni_appunti").document(next_s['id']).update({"ordine": sez.get('ordine', i+1)})
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
