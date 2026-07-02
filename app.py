import json
import random
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent
QUESTION_BANK_PATH = APP_DIR / "question_bank.json"
PROGRESS_PATH = APP_DIR / "progress.json"


st.set_page_config(
    page_title="Quiz Trainer",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="expanded",
)


def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_question(raw, index):
    options = raw.get("options", raw.get("choices", []))
    correct = raw.get("correct_answers", raw.get("correct", raw.get("answers", raw.get("answer"))))
    correct_answers = [str(item) for item in normalize_list(correct)]

    normalized_options = []
    if isinstance(options, dict):
        for key, value in options.items():
            normalized_options.append({"key": str(key), "text": str(value)})
    else:
        for option in normalize_list(options):
            if isinstance(option, dict):
                key = str(option.get("key", option.get("id", option.get("label", option.get("text", "")))))
                text = str(option.get("text", option.get("label", key)))
                normalized_options.append({"key": key, "text": text})
            else:
                text = str(option)
                normalized_options.append({"key": text, "text": text})

    option_keys = {item["key"] for item in normalized_options}
    option_texts = {item["text"] for item in normalized_options}
    cleaned_correct = []
    for answer in correct_answers:
        if answer in option_keys:
            cleaned_correct.append(answer)
        elif answer in option_texts:
            matching = next(item["key"] for item in normalized_options if item["text"] == answer)
            cleaned_correct.append(matching)
        else:
            cleaned_correct.append(answer)

    question_id = str(raw.get("id", raw.get("question_id", f"q-{index + 1}")))

    return {
        "id": question_id,
        "question": str(raw.get("question", raw.get("text", ""))).strip(),
        "topic": str(raw.get("topic", "General")).strip() or "General",
        "subtopic": str(raw.get("subtopic", "General")).strip() or "General",
        "difficulty": str(raw.get("difficulty", "Medium")).strip() or "Medium",
        "tags": [str(tag).strip() for tag in normalize_list(raw.get("tags")) if str(tag).strip()],
        "ambiguous": bool(raw.get("ambiguous", raw.get("is_ambiguous", False))),
        "options": normalized_options,
        "correct_answers": cleaned_correct,
        "explanation": str(raw.get("explanation", raw.get("why", "No explanation provided."))).strip(),
    }


@st.cache_data(show_spinner=False)
def load_question_bank():
    if not QUESTION_BANK_PATH.exists():
        return []

    with QUESTION_BANK_PATH.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        questions = payload.get("questions", payload.get("items", []))
    else:
        questions = payload

    return [
        normalize_question(question, index)
        for index, question in enumerate(questions)
        if isinstance(question, dict) and question.get("question", question.get("text"))
    ]


def load_progress():
    if not PROGRESS_PATH.exists():
        return {"answers": [], "exams": [], "failed_question_ids": [], "last_saved": None}
    try:
        with PROGRESS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"answers": [], "failed_question_ids": [], "last_saved": None}

    data.setdefault("answers", [])
    data.setdefault("exams", [])
    data.setdefault("failed_question_ids", [])
    data.setdefault("last_saved", None)
    return data


def save_progress(progress):
    progress["last_saved"] = datetime.now(timezone.utc).isoformat()
    with PROGRESS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2)


def reset_exam_state():
    st.session_state.exam_session = None


def all_values(questions, field):
    values = sorted({question[field] for question in questions if question[field]})
    return values


def all_tags(questions):
    values = set()
    for question in questions:
        values.update(question["tags"])
    return sorted(values)


def filter_questions(questions, selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode):
    filtered = []
    for question in questions:
        if selected_topics and question["topic"] not in selected_topics:
            continue
        if selected_subtopics and question["subtopic"] not in selected_subtopics:
            continue
        if selected_difficulties and question["difficulty"] not in selected_difficulties:
            continue
        if selected_tags and not set(selected_tags).issubset(set(question["tags"])):
            continue
        if ambiguous_mode in ("Exclude", "Excluir") and question["ambiguous"]:
            continue
        if ambiguous_mode in ("Only ambiguous", "Solo ambiguas") and not question["ambiguous"]:
            continue
        filtered.append(question)
    return filtered


def make_question_pool(mode, filtered_questions, progress):
    if not filtered_questions:
        return []

    if mode == "Adaptive mode":
        failed_ids = progress.get("failed_question_ids", [])
        failed_pool = [question for question in filtered_questions if question["id"] in failed_ids]
        other_pool = [question for question in filtered_questions if question["id"] not in failed_ids]
        random.shuffle(failed_pool)
        random.shuffle(other_pool)
        return failed_pool + other_pool

    pool = filtered_questions[:]
    random.shuffle(pool)
    return pool


def start_exam_session(mode, filtered_questions, progress, exam_size):
    pool = make_question_pool(mode, filtered_questions, progress)
    selected = pool[: min(exam_size, len(pool))]
    st.session_state.exam_session = {
        "id": str(uuid.uuid4()),
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "question_ids": [question["id"] for question in selected],
        "submitted": False,
        "results": [],
        "score": 0,
    }


def answer_is_correct(selected, correct_answers):
    return set(selected) == set(correct_answers)


def format_answers(question, answer_keys):
    labels = []
    for key in answer_keys:
        option = next((item for item in question["options"] if item["key"] == key), None)
        labels.append(option["text"] if option else key)
    return labels


def question_group(question):
    try:
        question_id = int(question["id"])
    except ValueError:
        return "other"
    start = ((question_id - 1) // 20) * 20 + 1
    end = start + 19
    return f"{start}-{end}"


def build_answer_record(exam_id, question, selected, is_correct):
    record = {
        "exam_id": exam_id,
        "question_id": question["id"],
        "question_group": question_group(question),
        "topic": question["topic"],
        "subtopic": question["subtopic"],
        "difficulty": question["difficulty"],
        "tags": question["tags"],
        "selected": selected,
        "correct_answers": question["correct_answers"],
        "is_correct": is_correct,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
    return record


def record_exam(progress, session, results):
    exam_id = session["id"]
    answered_at = datetime.now(timezone.utc).isoformat()
    records = [
        build_answer_record(exam_id, item["question"], item["selected"], item["is_correct"])
        for item in results
    ]

    for record in records:
        record["answered_at"] = answered_at

    progress["answers"].extend(records)

    failed_ids = set(progress.get("failed_question_ids", []))
    for item in results:
        question_id = item["question"]["id"]
        if item["is_correct"]:
            failed_ids.discard(question_id)
        else:
            failed_ids.add(question_id)
    progress["failed_question_ids"] = sorted(failed_ids)

    correct = sum(1 for item in results if item["is_correct"])
    total = len(results)
    progress["exams"].append(
        {
            "exam_id": exam_id,
            "mode": session["mode"],
            "started_at": session["started_at"],
            "submitted_at": answered_at,
            "questions": total,
            "correct": correct,
            "accuracy": correct / total if total else 0,
            "question_ids": [item["question"]["id"] for item in results],
        }
    )
    save_progress(progress)


def calculate_stats(progress):
    answers = progress.get("answers", [])
    total = len(answers)
    correct = sum(1 for answer in answers if answer.get("is_correct"))
    accuracy = correct / total if total else 0

    topic_totals = Counter(answer.get("topic", "General") for answer in answers)
    topic_misses = Counter(answer.get("topic", "General") for answer in answers if not answer.get("is_correct"))
    weak_topics = sorted(
        topic_misses.items(),
        key=lambda item: (item[1] / topic_totals[item[0]], item[1]),
        reverse=True,
    )
    return total, correct, accuracy, weak_topics


def summarize_records(records, field):
    grouped = defaultdict(lambda: {"answered": 0, "correct": 0})
    for record in records:
        value = record.get(field, "General")
        grouped[value]["answered"] += 1
        if record.get("is_correct"):
            grouped[value]["correct"] += 1

    rows = []
    for value, stats in sorted(grouped.items()):
        answered = stats["answered"]
        correct = stats["correct"]
        rows.append(
            {
                field: value,
                "answered": answered,
                "correct": correct,
                "missed": answered - correct,
                "accuracy": f"{correct / answered:.0%}" if answered else "0%",
            }
        )
    return rows


def render_header(total, correct, accuracy, filtered_count):
    st.title("Quiz Trainer")
    st.caption("Bloques de preguntas con corrección final, estadísticas por examen y progreso guardado.")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Respondidas", total)
    col_b.metric("Correctas", correct)
    col_c.metric("Precisión", f"{accuracy:.0%}" if total else "0%")
    col_d.metric("Preguntas activas", filtered_count)
    st.progress(accuracy if total else 0, text="Precisión total")


def render_sidebar(questions):
    st.sidebar.title("Filtros")
    selected_topics = st.sidebar.multiselect("Tema", all_values(questions, "topic"))
    selected_subtopics = st.sidebar.multiselect("Subtema", all_values(questions, "subtopic"))
    selected_difficulties = st.sidebar.multiselect("Dificultad", all_values(questions, "difficulty"))
    selected_tags = st.sidebar.multiselect("Tags", all_tags(questions))
    ambiguous_mode = st.sidebar.radio(
        "Preguntas ambiguas",
        ["Incluir", "Excluir", "Solo ambiguas"],
        horizontal=False,
    )

    st.sidebar.divider()
    mode = st.sidebar.radio(
        "Modo",
        ["Random quiz", "Topic quiz", "Adaptive mode", "Exam simulation"],
    )
    exam_size = st.sidebar.number_input("Preguntas por bloque", min_value=1, max_value=100, value=20, step=1)

    if mode == "Topic quiz" and not selected_topics:
        st.sidebar.info("Elige uno o más temas para Topic quiz.")

    return selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode, mode, int(exam_size)


def render_exam_form(session, questions_by_id, progress):
    questions = [questions_by_id[question_id] for question_id in session["question_ids"] if question_id in questions_by_id]
    st.subheader(f"Bloque de {len(questions)} preguntas")
    st.progress(0, text="La corrección se mostrará al enviar el bloque completo.")

    with st.form(f"exam-form-{session['id']}"):
        selected_by_question = {}
        unanswered = []

        for index, question in enumerate(questions, start=1):
            st.markdown(f"### {index}. {question['question']}")
            meta = [
                f"Tema: {question['topic']}",
                f"Subtema: {question['subtopic']}",
                f"Dificultad: {question['difficulty']}",
                f"Grupo: {question_group(question)}",
            ]
            if question["ambiguous"]:
                meta.append("Ambigua")
            st.caption(" | ".join(meta))

            option_labels = {option["text"]: option["key"] for option in question["options"]}
            widget_key = f"exam-{session['id']}-{question['id']}"
            if len(question["correct_answers"]) != 1:
                selected_labels = st.multiselect(
                    "Selecciona todas las correctas. Déjalo vacío si ninguna es correcta.",
                    list(option_labels.keys()),
                    key=widget_key,
                )
            else:
                selected_label = st.radio(
                    "Selecciona una respuesta",
                    list(option_labels.keys()),
                    index=None,
                    key=widget_key,
                )
                selected_labels = [selected_label] if selected_label else []

            selected_keys = [option_labels[label] for label in selected_labels]
            selected_by_question[question["id"]] = selected_keys
            if not selected_keys and question["correct_answers"]:
                unanswered.append(index)
            st.divider()

        submitted = st.form_submit_button("Corregir bloque", type="primary")

    if submitted:
        if unanswered:
            st.warning("Faltan preguntas por responder: " + ", ".join(str(item) for item in unanswered))
            return

        results = []
        for question in questions:
            selected = selected_by_question[question["id"]]
            is_correct = answer_is_correct(selected, question["correct_answers"])
            results.append({"question": question, "selected": selected, "is_correct": is_correct})

        record_exam(progress, session, results)
        st.session_state.exam_session["submitted"] = True
        st.session_state.exam_session["results"] = results
        st.session_state.exam_session["score"] = sum(1 for item in results if item["is_correct"])
        st.rerun()


def render_exam_results(session):
    results = session.get("results", [])
    total = len(results)
    correct = session.get("score", 0)
    accuracy = correct / total if total else 0

    st.subheader("Corrección del bloque")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Preguntas", total)
    col_b.metric("Correctas", correct)
    col_c.metric("Nota", f"{accuracy:.0%}" if total else "0%")
    st.progress(accuracy, text="Resultado del bloque")

    st.write("Resumen por tema de este bloque")
    session_records = [
        build_answer_record(session["id"], item["question"], item["selected"], item["is_correct"])
        for item in results
    ]
    st.dataframe(summarize_records(session_records, "topic"), use_container_width=True, hide_index=True)

    for index, item in enumerate(results, start=1):
        question = item["question"]
        if item["is_correct"]:
            st.success(f"{index}. Correcta")
        else:
            st.error(f"{index}. Incorrecta")
        st.markdown(f"**{question['question']}**")
        selected_text = format_answers(question, item["selected"])
        correct_text = format_answers(question, question["correct_answers"])
        st.write("Tu respuesta:", ", ".join(selected_text) if selected_text else "Ninguna")
        st.write("Respuesta correcta:", ", ".join(correct_text) if correct_text else "Ninguna")
        st.info(question["explanation"])

    if st.button("Empezar otro bloque", type="primary"):
        reset_exam_state()
        st.rerun()


def render_weak_topics(progress):
    total, _, _, weak_topics = calculate_stats(progress)
    if not total:
        st.write("Responde un bloque y aparecerán aquí tus puntos débiles.")
        return

    st.write("Ordenado por tasa de fallos y número de errores.")
    topic_totals = Counter(answer.get("topic", "General") for answer in progress["answers"])
    for topic, misses in weak_topics[:5]:
        answered = topic_totals[topic]
        miss_rate = misses / answered if answered else 0
        st.progress(miss_rate, text=f"{topic}: {misses}/{answered} falladas")


def render_statistics(progress):
    answers = progress.get("answers", [])
    exams = progress.get("exams", [])
    total, correct, accuracy, _ = calculate_stats(progress)

    st.subheader("Último examen")
    if exams:
        last_exam = exams[-1]
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Modo", last_exam.get("mode", "-"))
        col_b.metric("Preguntas", last_exam.get("questions", 0))
        col_c.metric("Correctas", last_exam.get("correct", 0))
        col_d.metric("Nota", f"{last_exam.get('accuracy', 0):.0%}")
    else:
        st.write("Todavía no hay exámenes guardados.")

    st.divider()
    st.subheader("Totales")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Exámenes", len(exams))
    col_b.metric("Preguntas respondidas", total)
    col_c.metric("Correctas", correct)
    col_d.metric("Precisión total", f"{accuracy:.0%}" if total else "0%")
    st.progress(accuracy if total else 0, text="Precisión total")

    st.divider()
    st.subheader("Por grupos")
    if answers:
        group_tab, topic_tab, subtopic_tab, difficulty_tab = st.tabs(["Bloques ID", "Tema", "Subtema", "Dificultad"])
        with group_tab:
            st.dataframe(summarize_records(answers, "question_group"), use_container_width=True, hide_index=True)
        with topic_tab:
            st.dataframe(summarize_records(answers, "topic"), use_container_width=True, hide_index=True)
        with subtopic_tab:
            st.dataframe(summarize_records(answers, "subtopic"), use_container_width=True, hide_index=True)
        with difficulty_tab:
            st.dataframe(summarize_records(answers, "difficulty"), use_container_width=True, hide_index=True)
    else:
        st.write("Responde un bloque para ver estadísticas por grupos.")

    st.divider()
    st.subheader("Historial de exámenes")
    if exams:
        rows = [
            {
                "exam": index + 1,
                "mode": exam.get("mode", "-"),
                "questions": exam.get("questions", 0),
                "correct": exam.get("correct", 0),
                "accuracy": f"{exam.get('accuracy', 0):.0%}",
                "submitted_at": exam.get("submitted_at", ""),
            }
            for index, exam in enumerate(exams)
        ]
        st.dataframe(list(reversed(rows)), use_container_width=True, hide_index=True)
    else:
        st.write("No hay historial todavía.")

    st.divider()
    st.subheader("Puntos débiles")
    render_weak_topics(progress)


def main():
    questions = load_question_bank()
    progress = load_progress()

    st.markdown(
        """
        <style>
        .stApp { background: #0f1218; }
        [data-testid="stSidebar"] { background: #151a22; }
        .stButton button { border-radius: 6px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not questions:
        st.title("Quiz Trainer")
        st.warning("Add a question_bank.json file next to app.py to begin.")
        st.code(
            """
{
  "questions": [
    {
      "id": "example-1",
      "topic": "Python",
      "subtopic": "Data types",
      "difficulty": "Easy",
      "tags": ["basics"],
      "ambiguous": false,
      "question": "Which type stores true/false values?",
      "options": ["str", "bool", "list", "dict"],
      "answer": "bool",
      "explanation": "The bool type represents True and False values."
    }
  ]
}
            """.strip(),
            language="json",
        )
        return

    sidebar_values = render_sidebar(questions)
    selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode, mode, exam_size = sidebar_values

    filtered_questions = filter_questions(
        questions,
        selected_topics,
        selected_subtopics,
        selected_difficulties,
        selected_tags,
        ambiguous_mode,
    )

    if mode == "Topic quiz" and selected_topics:
        filtered_questions = [question for question in filtered_questions if question["topic"] in selected_topics]

    if st.sidebar.button("Nuevo bloque"):
        reset_exam_state()

    if st.sidebar.button("Resetear progreso"):
        save_progress({"answers": [], "exams": [], "failed_question_ids": [], "last_saved": None})
        reset_exam_state()
        st.rerun()

    st.sidebar.download_button(
        "Descargar progreso",
        data=json.dumps(progress, indent=2),
        file_name="quiz_progress.json",
        mime="application/json",
    )

    total, correct, accuracy, _ = calculate_stats(progress)
    render_header(total, correct, accuracy, len(filtered_questions))

    tab_quiz, tab_stats, tab_bank = st.tabs(["Quiz", "Estadísticas", "Banco de preguntas"])

    with tab_quiz:
        if not filtered_questions:
            st.warning("No hay preguntas con los filtros actuales.")
        else:
            questions_by_id = {question["id"]: question for question in questions}
            session = st.session_state.get("exam_session")
            if not session:
                st.write(f"Pulsa iniciar para crear un bloque de {min(exam_size, len(filtered_questions))} preguntas.")
                if st.button("Iniciar bloque", type="primary"):
                    start_exam_session(mode, filtered_questions, progress, exam_size)
                    st.rerun()
            elif session.get("submitted"):
                render_exam_results(session)
            else:
                render_exam_form(session, questions_by_id, progress)

    with tab_stats:
        render_statistics(progress)

    with tab_bank:
        grouped = defaultdict(int)
        for question in filtered_questions:
            grouped[(question["topic"], question["subtopic"], question["difficulty"])] += 1
        rows = [
            {"topic": topic, "subtopic": subtopic, "difficulty": difficulty, "questions": count}
            for (topic, subtopic, difficulty), count in sorted(grouped.items())
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
