"""
このファイルは、画面表示以外の様々な関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import os
from dotenv import load_dotenv
import streamlit as st
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
import constants as ct


############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
load_dotenv()


############################################################
# 関数定義
############################################################

def get_source_icon(source):
    """
    メッセージと一緒に表示するアイコンの種類を取得

    Args:
        source: 参照元のありか

    Returns:
        メッセージと一緒に表示するアイコンの種類
    """
    # 参照元がWebページの場合とファイルの場合で、取得するアイコンの種類を変える
    if source.startswith("http"):
        icon = ct.LINK_SOURCE_ICON
    else:
        icon = ct.DOC_SOURCE_ICON
    
    return icon


# 問題4 参照ページの表示
def is_pdf_file(file_path):
    """
    ファイルパスがPDFファイルかどうかを判定

    Args:
        file_path: ファイルパス

    Returns:
        PDFファイルの場合True、そうでなければFalse
    """
    return file_path.lower().endswith('.pdf')


# 問題4 参照ページの表示
def format_source_with_page(file_path, page_number=None):
    """
    ファイルパスとページ番号を組み合わせて表示用の文字列を作成

    Args:
        file_path: ファイルパス
        page_number: ページ番号（PDFファイルの場合のみ）

    Returns:
        表示用の文字列
    """
    if is_pdf_file(file_path) and page_number is not None:
        return f"{file_path} （ページNo.{page_number}）"
    else:
        return file_path


def build_error_message(message):
    """
    エラーメッセージと管理者問い合わせテンプレートの連結

    Args:
        message: 画面上に表示するエラーメッセージ

    Returns:
        エラーメッセージと管理者問い合わせテンプレートの連結テキスト
    """
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])


def get_llm_response(chat_message):
    """
    LLMからの回答取得

    Args:
        chat_message: ユーザー入力値

    Returns:
        LLMからの回答
    """
    # LLMのオブジェクトを用意
    llm = ChatOpenAI(model_name=ct.MODEL, temperature=ct.TEMPERATURE)

    # 会話履歴なしでもLLMに理解してもらえる、独立した入力テキストを取得するためのプロンプトテンプレートを作成
    question_generator_template = ct.SYSTEM_PROMPT_CREATE_INDEPENDENT_TEXT
    question_generator_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", question_generator_template),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # モードによってLLMから回答を取得する用のプロンプトを変更
    if st.session_state.mode == ct.ANSWER_MODE_1:
        # モードが「社内文書検索」の場合のプロンプト
        question_answer_template = ct.SYSTEM_PROMPT_DOC_SEARCH
    else:
        # モードが「社内問い合わせ」の場合のプロンプト
        question_answer_template = ct.SYSTEM_PROMPT_INQUIRY
    # LLMから回答を取得する用のプロンプトテンプレートを作成
    question_answer_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", question_answer_template),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # Retrieverが利用できない場合のチェック
    if "retriever" not in st.session_state or st.session_state.retriever is None:
        # RAG機能が利用できない場合のシンプルなチャット機能
        llm = ChatOpenAI(model=ct.MODEL_NAME, temperature=ct.TEMPERATURE)
        
        # シンプルなプロンプト（RAG機能なし）
        simple_prompt = ChatPromptTemplate.from_messages([
            ("system", "あなたは親切なアシスタントです。ユーザーの質問に丁寧に答えてください。"),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ])
        
        # シンプルなチェーンを作成
        chain = simple_prompt | llm
        
        # レスポンス取得
        llm_response = chain.invoke({
            "input": chat_message, 
            "chat_history": st.session_state.chat_history
        })
        
        # 会話履歴に追加
        st.session_state.chat_history.extend([
            HumanMessage(content=chat_message), 
            AIMessage(content=llm_response.content)
        ])
        
        # RAG機能なしのレスポンス形式に合わせる
        return {
            "answer": llm_response.content,
            "context": []  # 空のコンテキスト
        }

    # 会話履歴なしでもLLMに理解してもらえる、独立した入力テキストを取得するためのRetrieverを作成
    history_aware_retriever = create_history_aware_retriever(
        llm, st.session_state.retriever, question_generator_prompt
    )

    # LLMから回答を取得する用のChainを作成
    question_answer_chain = create_stuff_documents_chain(llm, question_answer_prompt)
    # 「RAG x 会話履歴の記憶機能」を実現するためのChainを作成
    chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    # LLMへのリクエストとレスポンス取得
    llm_response = chain.invoke({"input": chat_message, "chat_history": st.session_state.chat_history})
    # LLMレスポンスを会話履歴に追加
    st.session_state.chat_history.extend([HumanMessage(content=chat_message), llm_response["answer"]])

    return llm_response