import streamlit as st
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date, timedelta

# ==========================================
# INIZIALIZZAZIONE FIREBASE
# ==========================================
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("firebase_key.json")
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Errore di connessione a Firebase: Assicurati che 'firebase_key.json' sia nella cartella. Dettagli: {e}")

db = firestore.client()

# Configurazione della pagina
st.set_page_config(page_title="Gestionale Progetti Cloud", page_icon="📋", layout="wide")

# ==========================================
# GESTIONE SESSIONE & ANTI-SPAM GIORNALIERO
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
# FUNZIONE PER LE NOTIFICHE BROWSER (JS)
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
                if (permission === "granted") {{
                    mostraPopup();
                }}
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
# LOGIN SEMPLIFICATO
# ==========================================
def schermata_login():
    st.title("🔐 Accesso al Gestionale Cloud")
    st.markdown("Inserisci la tua email per accedere o simulare la sessione di lavoro.")
    
    with st.form("form_login"):
        email = st.text_input("Email utente")
        btn_login = st.form_submit_button("Entra nel Gestionale")
        
        if btn_login and email:
            st.session_state.utente_loggato = email.strip()
            st.success("Accesso effettuato!")
            st.rerun()
        elif btn_login:
            st.error("Inserisci un'email valida.")

# ==========================================
# SELETTORE / GESTIONE BOARD & PERMESSI
# ==========================================
def schermata_selezione_board():
    st.title(f"👋 Benvenuto, {st.session_state.utente_loggato}")
    st.markdown("Seleziona una board a cui accedere o creane una nuova. I proprietari possono gestire i membri direttamente da qui.")

    with st.expander("➕ Crea una Nuova Board"):
        with st.form("form_nuova_board"):
            nome_board = st.text_input("Nome Board (es. Lavori Personali o Team Progetto X)")
            membri_extra = st.text_input("Membri aggiuntivi (inserisci email separate da virgola)")
            btn_crea_b = st.form_submit_button("Crea Board")

            if btn_crea_b and nome_board:
                lista_membri = [st.session_state.utente_loggato]
                if membri_extra:
                    extra = [m.strip() for m in membri_extra.split(",") if m.strip()]
                    lista_membri.extend(extra)
                
                db.collection("board").add({
                    "nome": nome_board,
                    "proprietario": st.session_state.utente_loggato,
                    "membri": list(set(lista_membri))
                })
                st.success(f"Board '{nome_board}' creata con successo!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Le tue Board Disponibili")

    board_docs = db.collection("board").stream()
    mie_board = []
    for b in board_docs:
        b_data = b.to_dict()
        membri = b_data.get("membri", [])
        if st.session_state.utente_loggato in membri:
            mie_board.append({"id": b.id, **b_data})

    if not mie_board:
        st.info("Non fai parte di alcuna board. Creane una usando il modulo in alto per iniziare!")
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
                    if st.button("Entra nella Board", key=f"entra_b_{b_id}"):
                        st.session_state.board_attiva_id = b_id
                        st.session_state.board_attiva_nome = b['nome']
                        st.rerun()

                # Se l'utente loggato è il PROPRIETARIO, mostriamo i controlli di gestione accessi
                if is_proprietario:
                    with st.expander(f"⚙️ Gestione Accessi & Membri ({b['nome']})"):
                        membri_attuali = b.get("membri", [])
                        
                        st.markdown("**Invita un nuovo membro:**")
                        with st.form(f"form_invito_{b_id}"):
                            nuova_email = st.text_input("Email nuovo utente", key=f"email_{b_id}")
                            btn_invita = st.form_submit_button("Aggiungi alla Board")
                            if btn_invita and nuova_email:
                                e_pulita = nuova_email.strip()
                                if e_pulita not in membri_attuali:
                                    membri_attuali.append(e_pulita)
                                    db.collection("board").document(b_id).update({"membri": membri_attuali})
                                    st.success(f"Utente {e_pulita} aggiunto con successo!")
                                    st.rerun()
                                else:
                                    st.warning("L'utente è già membro di questa board.")

                        st.markdown("---")
                        st.markdown("**Rimuovi membri:**")
                        for m in membri_attuali:
                            c_m1, c_m2 = st.columns([3, 1])
                            with c_m1:
                                st.text(m + (" (Proprietario)" if m == proprietario else ""))
                            with c_m2:
                                # Non permettiamo al proprietario di rimuovere se stesso per errore
                                if m != proprietario:
                                    if st.button("Rimuovi", key=f"rem_{b_id}_{m}"):
                                        membri_attuali.remove(m)
                                        db.collection("board").document(b_id).update({"membri": membri_attuali})
                                        st.success(f"Membro {m} rimosso.")
                                        st.rerun()

    st.markdown("---")
    if st.button("🚪 Esci (Logout)"):
        st.session_state.utente_loggato = None
        st.session_state.board_attiva_id = None
        st.session_state.board_attiva_nome = None
        st.rerun()

# ==========================================
# INTERFACCIA PRINCIPALE DELLA BOARD ATTIVA
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
    menu = st.sidebar.radio(
        "Seleziona Vista:",
        ["📋 Board Progetti (Kanban)", "⏳ Board Scadenze", "📅 Calendario", "📁 Progetti"]
    )
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Esci (Logout)"):
        st.session_state.utente_loggato = None
        st.session_state.board_attiva_id = None
        st.session_state.board_attiva_nome = None
        st.rerun()

    id_board = st.session_state.board_attiva_id

    # --- 1. BOARD PROGETTI KANBAN ---
    if menu == "📋 Board Progetti (Kanban)":
        st.header(f"📋 Board Progetti Kanban - {st.session_state.board_attiva_nome}")

        progetti_dict = {doc.id: doc.to_dict() for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
        progetti_lista = [{"id": p_id, **p_data} for p_id, p_data in progetti_dict.items()]

        if not progetti_lista:
            st.info("Nessun progetto trovato in questa board. Vai nella scheda 'Progetti' per crearne uno!")
        else:
            colonne = st.columns(len(progetti_lista))
            chiavi_renderizzate = set()
            
            for idx, prog in enumerate(progetti_lista):
                prog_id = prog['id']
                with colonne[idx]:
                    st.markdown(f"### 📁 {prog['nome']}")
                    if prog.get('descrizione'):
                        st.caption(prog['descrizione'])
                    st.markdown("---")

                    tasks_docs = db.collection("task").where("id_progetto", "==", prog_id).stream()
                    
                    for t_doc in tasks_docs:
                        t_data = t_doc.to_dict()
                        t_id = t_doc.id
                        stato_icona = "✅" if t_data.get("completata") == 1 else "⏳"
                        
                        btn_key_comp = f"btn_comp_{prog_id}_{t_id}"
                        btn_key_rip = f"btn_rip_{prog_id}_{t_id}"
                        
                        if btn_key_comp in chiavi_renderizzate or btn_key_rip in chiavi_renderizzate:
                            continue
                        chiavi_renderizzate.add(btn_key_comp)
                        chiavi_renderizzate.add(btn_key_rip)
                        
                        with st.container(border=True):
                            st.markdown(f"{stato_icona} **{t_data.get('titolo')}**")
                            
                            sezione_collegata = t_data.get("sezione_nome")
                            if sezione_collegata and sezione_collegata != "Nessuna":
                                st.caption(f"🔗 Sezione: **{sezione_collegata}**")
                                
                            assegnatario = t_data.get("assegnatario", "Non assegnato")
                            st.caption(f"👤 Assegnato a: **{assegnatario}**")
                            st.caption(f"Scad: {t_data.get('scadenza', 'Nessuna')}")
                            
                            if t_data.get("completata") == 0:
                                if st.button("Completa", key=btn_key_comp):
                                    db.collection("task").document(t_id).update({"completata": 1})
                                    st.rerun()
                            else:
                                if st.button("Ripristina", key=btn_key_rip):
                                    db.collection("task").document(t_id).update({"completata": 0})
                                    st.rerun()

                    with st.expander("➕ Aggiungi Task"):
                        sez_docs = db.collection("sezioni_appunti").where("id_progetto", "==", prog_id).stream()
                        sez_dict = {s.id: s.to_dict()['nome'] for s in sez_docs}
                        opzioni_sezioni = ["Nessuna"] + list(sez_dict.values())

                        with st.form(f"form_task_{prog_id}"):
                            titolo_task = st.text_input("Titolo Task", placeholder="Es. Fare questa cosa...")
                            sezione_scelta = st.selectbox("Collega a Sezione Appunti", opzioni_sezioni)
                            assegnatario_task = st.text_input("Assegnato a (Email / Nome)", value=st.session_state.utente_loggato)
                            
                            usa_scadenza = st.checkbox("Imposta Scadenza", value=True)
                            scadenza_task = st.date_input("Scadenza")
                            preavviso_task = st.number_input("Preavviso (giorni prima)", min_value=0, max_value=30, value=3)
                            
                            btn_aggiungi_task = st.form_submit_button("Salva Task")
                            
                            if btn_aggiungi_task and titolo_task:
                                db.collection("task").add({
                                    "id_progetto": prog_id,
                                    "titolo": titolo_task,
                                    "sezione_nome": sezione_scelta,
                                    "assegnatario": assegnatario_task,
                                    "scadenza": scadenza_task.strftime("%Y-%m-%d") if usa_scadenza else "",
                                    "preavviso": preavviso_task,
                                    "completata": 0
                                })
                                st.success("Task aggiunta!")
                                st.rerun()

    # --- 2. BOARD SCADENZE ---
    elif menu == "⏳ Board Scadenze":
        st.header("⏳ Board Scadenze - Vista Kanban")
        st.markdown("Panoramica di tutte le task della board suddivise per imminenza.")

        progetti_dict = {doc.id: doc.to_dict().get('nome', 'Senza Nome') for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
        
        tasks_lista = []
        if progetti_dict:
            tasks_docs = db.collection("task").stream()
            oggi = date.today()
            task_da_notificare = []

            for t in tasks_docs:
                t_data = t.to_dict()
                if t_data.get("id_progetto") in progetti_dict:
                    t_item = {
                        "id": t.id,
                        **t_data,
                        "progetto_nome": progetti_dict[t_data.get("id_progetto")]
                    }
                    
                    scad_str = t_data.get("scadenza", "")
                    completata = t_data.get("completata", 0)
                    preavviso = t_data.get("preavviso", 3)
                    
                    if not scad_str:
                        t_item["categoria"] = "no_scadenza"
                    else:
                        try:
                            data_scad = datetime.strptime(scad_str, "%Y-%m-%d").date()
                            giorni_diff = (data_scad - oggi).days
                            
                            if completata == 0 and giorni_diff <= preavviso:
                                task_da_notificare.append(t_item)

                            if giorni_diff <= 0:
                                t_item["categoria"] = "scadute_oggi"
                            elif giorni_diff <= 7:
                                t_item["categoria"] = "questa_settimana"
                            else:
                                t_item["categoria"] = "prossime_settimane"
                        except:
                            t_item["categoria"] = "no_scadenza"
                    
                    tasks_lista.append(t_item)

            if task_da_notificare:
                attiva_notifiche_browser(task_da_notificare)

        col_scadute_oggi_lista = [t for t in tasks_lista if t.get("categoria") == "scadute_oggi"]
        col_questa_settimana_lista = [t for t in tasks_lista if t.get("categoria") == "questa_settimana"]
        col_prossime_settimane_lista = [t for t in tasks_lista if t.get("categoria") == "prossime_settimane"]
        col_no_scadenza_lista = [t for t in tasks_lista if t.get("categoria") == "no_scadenza"]

        chiavi_scadenze_renderizzate = set()
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.markdown("### 🚨 Scadute / Oggi")
            st.markdown("---")
            if not col_scadute_oggi_lista:
                st.info("Nessuna task in scadenza immediata.")
            else:
                for t in col_scadute_oggi_lista:
                    btn_comp = f"s_comp_{t['id']}"
                    btn_rip = f"s_rip_{t['id']}"
                    if btn_comp in chiavi_scadenze_renderizzate: continue
                    chiavi_scadenze_renderizzate.add(btn_comp)

                    stato_icona = "✅" if t.get("completata") == 1 else "⏳"
                    with st.container(border=True):
                        st.markdown(f"{stato_icona} **{t['titolo']}**")
                        st.caption(f"📁 {t['progetto_nome']} | 👤 {t.get('assegnatario', 'N/D')}")
                        st.caption(f"📅 Scad: {t['scadenza']}")
                        
                        if t.get("completata") == 0:
                            if st.button("Completa", key=btn_comp):
                                db.collection("task").document(t['id']).update({"completata": 1})
                                st.rerun()
                        else:
                            if st.button("Ripristina", key=btn_rip):
                                db.collection("task").document(t['id']).update({"completata": 0})
                                st.rerun()

        with c2:
            st.markdown("### ⚠️ Questa Settimana")
            st.markdown("---")
            if not col_questa_settimana_lista:
                st.info("Nessuna task per questa settimana.")
            else:
                for t in col_questa_settimana_lista:
                    btn_comp = f"s_comp_{t['id']}"
                    btn_rip = f"s_rip_{t['id']}"
                    if btn_comp in chiavi_scadenze_renderizzate: continue
                    chiavi_scadenze_renderizzate.add(btn_comp)

                    stato_icona = "✅" if t.get("completata") == 1 else "⏳"
                    with st.container(border=True):
                        st.markdown(f"{stato_icona} **{t['titolo']}**")
                        st.caption(f"📁 {t['progetto_nome']} | 👤 {t.get('assegnatario', 'N/D')}")
                        st.caption(f"📅 Scad: {t['scadenza']}")
                        
                        if t.get("completata") == 0:
                            if st.button("Completa", key=btn_comp):
                                db.collection("task").document(t['id']).update({"completata": 1})
                                st.rerun()
                        else:
                            if st.button("Ripristina", key=btn_rip):
                                db.collection("task").document(t['id']).update({"completata": 0})
                                st.rerun()

        with c3:
            st.markdown("### 📅 Prossime Settimane")
            st.markdown("---")
            if not col_prossime_settimane_lista:
                st.info("Nessuna task a lungo termine.")
            else:
                for t in col_prossime_settimane_lista:
                    btn_comp = f"s_comp_{t['id']}"
                    btn_rip = f"s_rip_{t['id']}"
                    if btn_comp in chiavi_scadenze_renderizzate: continue
                    chiavi_scadenze_renderizzate.add(btn_comp)

                    stato_icona = "✅" if t.get("completata") == 1 else "⏳"
                    with st.container(border=True):
                        st.markdown(f"{stato_icona} **{t['titolo']}**")
                        st.caption(f"📁 {t['progetto_nome']} | 👤 {t.get('assegnatario', 'N/D')}")
                        st.caption(f"📅 Scad: {t['scadenza']}")
                        
                        if t.get("completata") == 0:
                            if st.button("Completa", key=btn_comp):
                                db.collection("task").document(t['id']).update({"completata": 1})
                                st.rerun()
                        else:
                            if st.button("Ripristina", key=btn_rip):
                                db.collection("task").document(t['id']).update({"completata": 0})
                                st.rerun()

        with c4:
            st.markdown("### 📌 No Scadenza")
            st.markdown("---")
            if not col_no_scadenza_lista:
                st.info("Nessuna task senza scadenza.")
            else:
                for t in col_no_scadenza_lista:
                    btn_comp = f"s_comp_{t['id']}"
                    btn_rip = f"s_rip_{t['id']}"
                    if btn_comp in chiavi_scadenze_renderizzate: continue
                    chiavi_scadenze_renderizzate.add(btn_comp)

                    stato_icona = "✅" if t.get("completata") == 1 else "⏳"
                    with st.container(border=True):
                        st.markdown(f"{stato_icona} **{t['titolo']}**")
                        st.caption(f"📁 {t['progetto_nome']} | 👤 {t.get('assegnatario', 'N/D')}")
                        st.caption("📅 Scad: Nessuna")
                        
                        if t.get("completata") == 0:
                            if st.button("Completa", key=btn_comp):
                                db.collection("task").document(t['id']).update({"completata": 1})
                                st.rerun()
                        else:
                            if st.button("Ripristina", key=btn_rip):
                                db.collection("task").document(t['id']).update({"completata": 0})
                                st.rerun()

    # --- 3. CALENDARIO ---
    elif menu == "📅 Calendario":
        st.header("📅 Calendario Scadenze")
        st.markdown("Visualizzazione a griglia mensile di tutte le task programmate.")

        try:
            from streamlit_calendar import calendar
        except ImportError:
            calendar = None

        if calendar:
            progetti_dict = {doc.id: doc.to_dict().get('nome', 'Progetto') for doc in db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()}
            events = []
            if progetti_dict:
                tasks_docs = db.collection("task").stream()
                for t in tasks_docs:
                    t_data = t.to_dict()
                    if t_data.get("id_progetto") in progetti_dict:
                        scad_str = t_data.get("scadenza", "")
                        if scad_str:
                            titolo = t_data.get("titolo", "Senza titolo")
                            prog_nome = progetti_dict[t_data.get("id_progetto")]
                            assegnatario = t_data.get("assegnatario", "")
                            completata = t_data.get("completata", 0)
                            
                            colore = "#28a745" if completata == 1 else "#007bff"
                            etichetta_evento = f"[{prog_nome}] {titolo}"
                            if assegnatario:
                                etichetta_evento += f" (👤 {assegnatario})"

                            events.append({
                                "title": etichetta_evento,
                                "start": scad_str,
                                "end": scad_str,
                                "backgroundColor": colore,
                                "borderColor": colore
                            })

            calendar_options = {
                "editable": False,
                "selectable": True,
                "headerToolbar": {
                    "left": "today prev,next",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay"
                },
                "initialView": "dayGridMonth",
            }
            calendar(events=events, options=calendar_options, key="calendario_task")

    # --- 4. PROGETTI E SEZIONI ---
    elif menu == "📁 Progetti":
        st.header(f"📁 Gestione Progetti - {st.session_state.board_attiva_nome}")
        st.markdown("Crea e gestisci i progetti di questa board, organizza gli appunti.")

        with st.expander("➕ Crea un Nuovo Progetto in questa Board"):
            with st.form("form_nuovo_progetto"):
                nome_prog = st.text_input("Nome Progetto (es. Progetto Test)")
                desc_prog = st.text_area("Descrizione generale")
                btn_crea_prog = st.form_submit_button("Crea Progetto")
                if btn_crea_prog and nome_prog:
                    db.collection("progetti").add({
                        "id_board": id_board,
                        "nome": nome_prog,
                        "descrizione": desc_prog,
                        "proprietario": st.session_state.utente_loggato,
                        "archiviato": 0
                    })
                    st.success(f"Progetto '{nome_prog}' creato con successo!")
                    st.rerun()

        st.markdown("---")

        progetti_docs = db.collection("progetti").where("id_board", "==", id_board).where("archiviato", "==", 0).stream()
        progetti_dict = {doc.id: doc.to_dict() for doc in progetti_docs}

        if not progetti_dict:
            st.info("Nessun progetto trovato in questa board. Creane uno usando il modulo in alto!")
        else:
            nomi_progetti = {p_data['nome']: p_id for p_id, p_data in progetti_dict.items()}
            scelta_nome_prog = st.selectbox("Seleziona Progetto da gestire", list(nomi_progetti.keys()))
            id_prog_selezionato = nomi_progetti[scelta_nome_prog]

            dati_prog_selezionato = progetti_dict[id_prog_selezionato]
            st.markdown(f"### ⚙️ Gestione Progetto: *{scelta_nome_prog}*")
            if dati_prog_selezionato.get('descrizione'):
                st.info(f"**Descrizione:** {dati_prog_selezionato['descrizione']}")

            if st.button("🗑️ Elimina Intero Progetto (e dati associati)", type="primary"):
                db.collection("progetti").document(id_prog_selezionato).delete()
                
                sez_da_eliminare = db.collection("sezioni_appunti").where("id_progetto", "==", id_prog_selezionato).stream()
                for s in sez_da_eliminare:
                    db.collection("sezioni_appunti").document(s.id).delete()
                    
                task_da_eliminare = db.collection("task").where("id_progetto", "==", id_prog_selezionato).stream()
                for t in task_da_eliminare:
                    db.collection("task").document(t.id).delete()
                    
                st.success(f"Progetto '{scelta_nome_prog}' eliminato con successo!")
                st.rerun()

            st.markdown("---")

            col_alto_1, col_alto_2 = st.columns([3, 1])
            with col_alto_1:
                st.subheader("📖 Sezioni e Appunti del Progetto")
            with col_alto_2:
                with st.expander("➕ Nuova Sezione"):
                    with st.form(f"form_nuova_sezione_{id_prog_selezionato}"):
                        nome_sezione = st.text_input("Nome Sezione (es. WP 1)")
                        contenuto_sezione = st.text_area("Contenuto Appunti", height=120)
                        
                        sezioni_esistenti = list(db.collection("sezioni_appunti").where("id_progetto", "==", id_prog_selezionato).stream())
                        nuovo_ordine = len(sezioni_esistenti) + 1
                        
                        btn_salva_sezione = st.form_submit_button("Salva Sezione")

                        if btn_salva_sezione and nome_sezione:
                            db.collection("sezioni_appunti").add({
                                "id_progetto": id_prog_selezionato,
                                "nome": nome_sezione,
                                "contenuto": contenuto_sezione,
                                "ordine": nuovo_ordine,
                                "autore": st.session_state.utente_loggato
                            })
                            st.success("Sezione aggiunta!")
                            st.rerun()

            sezioni_docs = db.collection("sezioni_appunti").where("id_progetto", "==", id_prog_selezionato).stream()
            sezioni_lista = [{"id": s.id, **s.to_dict()} for s in sezioni_docs]
            sezioni_lista = sorted(sezioni_lista, key=lambda x: x.get('ordine', 0))

            if not sezioni_lista:
                st.info("Nessuna sezione creata per questo progetto. Clicca su '➕ Nuova Sezione' in alto a destra per iniziare.")
            else:
                for index, sez in enumerate(sezioni_lista):
                    with st.container(border=True):
                        c_testo, c_bottoni = st.columns([5, 1])
                        
                        with c_testo:
                            st.markdown(f"### 📌 {sez['nome']}")
                            st.write(sez['contenuto'])
                            st.caption(f"Autore: {sez.get('autore', 'N/D')}")
                            
                        with c_bottoni:
                            st.markdown("**Ordina:**")
                            if index > 0:
                                if st.button("⬆️ Su", key=f"up_{sez['id']}"):
                                    prev_sez = sezioni_lista[index - 1]
                                    db.collection("sezioni_appunti").document(sez['id']).update({"ordine": prev_sez.get('ordine', index)})
                                    db.collection("sezioni_appunti").document(prev_sez['id']).update({"ordine": sez.get('ordine', index + 1)})
                                    st.rerun()
                            
                            if index < len(sezioni_lista) - 1:
                                if st.button("⬇️ Giù", key=f"down_{sez['id']}"):
                                    next_sez = sezioni_lista[index + 1]
                                    db.collection("sezioni_appunti").document(sez['id']).update({"ordine": next_sez.get('ordine', index + 2)})
                                    db.collection("sezioni_appunti").document(next_sez['id']).update({"ordine": sez.get('ordine', index + 1)})
                                    st.rerun()
                                    
                            st.markdown("---")
                            if st.button("🗑️ Elimina", key=f"del_sez_{sez['id']}"):
                                db.collection("sezioni_appunti").document(sez['id']).delete()
                                st.rerun()

# ==========================================
# GESTIONE FLUSSO PRINCIPALE
# ==========================================
if st.session_state.utente_loggato is None:
    schermata_login()
elif st.session_state.board_attiva_id is None:
    schermata_selezione_board()
else:
    schermata_principale()