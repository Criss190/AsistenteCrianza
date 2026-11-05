import json, os, sys
sys.path.insert(0, "/app")
from datasets import Dataset
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from ragas.embeddings.base import LangchainEmbeddingsWrapper
from ragas.llms.base import LangchainLLMWrapper
from ragas.run_config import RunConfig
from src.rag_chat import ChatRAG

datos = json.load(open("/app/eval_dataset_quick.json"))
chat = ChatRAG(chunk_size=500, chunk_overlap=50, top_k=3)
print("api_key configurada:", bool(chat.api_key))

filas = []
for f in datos:
    r = chat.responder(f["question"])
    filas.append({**f, "contexts": r["contexts"], "answer": r["answer"], "mode": r["mode"]})
    print(f["question"][:50], "->", r["mode"])

en_dominio = [f for f in filas if "La información no se encuentra" not in f["ground_truth"]]
conjunto = Dataset.from_list([
    {k: f[k] for k in ("question", "contexts", "answer", "ground_truth")}
    for f in en_dominio
])

juez = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0, max_retries=6, timeout=120)
embeddings = LangchainEmbeddingsWrapper(GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", max_retries=6))
juez_ragas = LangchainLLMWrapper(juez)
for m in (faithfulness, answer_relevancy, context_precision, context_recall):
    m.llm = juez_ragas

resultado = evaluate(
    conjunto,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    llm=juez_ragas,
    embeddings=embeddings,
    run_config=RunConfig(timeout=180, max_retries=6, max_workers=1),
    raise_exceptions=False,
)
print(resultado)
df = resultado.to_pandas()
df.to_json("/app/quick_results.json", orient="records", indent=2, force_ascii=False)
print(df.to_string())
