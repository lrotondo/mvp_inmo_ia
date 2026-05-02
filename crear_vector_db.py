from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_community.document_loaders import DataFrameLoader
from langchain_community.vectorstores import Chroma

_CONFIG_ENV = Path(__file__).resolve().parent / "config.env"
_CSV_CANDIDATES = ["propiedades.csv", "propiedades_vivas.csv"]


def resolve_input_csv() -> Path:
    base_dir = Path(__file__).resolve().parent
    for candidate in _CSV_CANDIDATES:
        path = base_dir / candidate
        if path.exists():
            try:
                preview_df = pd.read_csv(path)
                if not preview_df.empty:
                    return path
            except Exception:
                pass
            # Si existe pero no tiene filas, seguimos buscando otro candidato.
            continue
    return base_dir / _CSV_CANDIDATES[0]


def main() -> None:
    load_dotenv(_CONFIG_ENV, override=True)
    # Cargar tu CSV
    input_csv = resolve_input_csv()
    df = pd.read_csv(input_csv)
    if df.empty:
        raise RuntimeError(
            f"El CSV '{input_csv.name}' no tiene filas. Generá propiedades primero."
        )

    # Creamos una columna robusta para la búsqueda semántica.
    # Incluimos ID y Link para que la IA los tenga a mano al responder.
    df["content"] = df.apply(
        lambda x: (
            f"Propiedad ID: {x['ID']}. Ubicación: {x['Direccion']} en {x['Barrio']}. "
            f"Precio: {x['Precio']}. Ambientes: {x['Ambientes']}. "
            f"Características: {x['Caracteristicas']}. "
            f"Link de foto: {x['Link_Fotos']}"
        ),
        axis=1,
    )

    # Inicializar cargador y embeddings
    loader = DataFrameLoader(df, page_content_column="content")
    documents = loader.load()

    # Crear la base de datos vectorial local (ChromaDB).
    # Usamos embeddings locales de Chroma para evitar errores con providers
    # que no exponen endpoint de embeddings compatible.
    vector_db = Chroma.from_documents(documents, persist_directory="./db_tandil")
    print(f"Base vectorial creada en ./db_tandil desde {input_csv.name}")


if __name__ == "__main__":
    main()
