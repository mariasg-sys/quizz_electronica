# Streamlit Quiz Trainer

This app loads `question_bank.json`, filters questions, runs quiz blocks, corrects the whole block at the end, explains answers, tracks per-exam and total stats, and saves progress locally in `progress.json`.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Question Bank Format

Put your final `question_bank.json` next to `app.py`. The app accepts either a top-level list of questions or:

```json
{
  "questions": [
    {
      "id": "q1",
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
```

For multiple-correct questions, use `correct_answers`:

```json
"correct_answers": ["list", "tuple"]
```

Options can be strings, a dictionary, or objects with `key` and `text`.

## Quiz Flow

The quiz is now organized in blocks. By default each block has 20 questions:

1. Choose filters and mode in the sidebar.
2. Click `Iniciar bloque`.
3. Answer all questions in the block.
4. Click `Corregir bloque`.
5. Review score, correct answers, explanations, and the block summary.

## Quiz Modes

- Random quiz: picks from the active filtered pool.
- Topic quiz: works with the selected sidebar topic filters.
- Adaptive mode: prioritizes questions missed in previous attempts.
- Exam simulation: builds a shuffled exam block from the filtered pool.

## Statistics

The statistics tab includes:

- Latest exam result.
- Total questions, correct answers, and overall accuracy.
- Grouped stats by question ID block, topic, subtopic, and difficulty.
- Exam history.
- Weak topics ranked by miss rate.

## Progress

Progress is saved locally to `progress.json`. Use the sidebar buttons to reset or download it.

## Phone Use

Streamlit apps are web apps, not direct installable mobile apps by default. You can still use it on a phone by running Streamlit on a computer/server and opening the app URL from the phone browser. Many mobile browsers also let you add the page to the home screen.
