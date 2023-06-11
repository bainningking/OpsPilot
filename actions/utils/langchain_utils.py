from langchain.agents import load_tools, AgentType, initialize_agent
from langchain.chat_models import AzureChatOpenAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.tools import Tool
from langchain.utilities import BingSearchAPIWrapper
from langchain.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain import OpenAI, VectorDBQA, PromptTemplate, LLMChain
from langchain.document_loaders import DirectoryLoader
from langchain.chains import RetrievalQA, LLMRequestsChain

from actions.constant.server_settings import server_settings


def load_docsearch():
    loader = DirectoryLoader('./llm_data', glob='**/*.txt', show_progress=True)
    documents = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=100, chunk_overlap=0)
    split_docs = text_splitter.split_documents(documents)
    embeddings = OpenAIEmbeddings(model='text-embedding-ada-002',
                                  deployment='ada',
                                  openai_api_base=server_settings.azure_openai_endpoint,
                                  openai_api_type='azure',
                                  openai_api_key=server_settings.azure_openai_key,
                                  chunk_size=1)
    doc_search = Chroma.from_documents(split_docs, embeddings)
    return doc_search


def langchain_qa(doc_search, query):
    llm = AzureChatOpenAI(openai_api_base=server_settings.azure_openai_endpoint,
                          openai_api_key=server_settings.azure_openai_key,
                          deployment_name=server_settings.azure_openai_model_name, temperature=0.7,
                          openai_api_version="2023-05-15")
    qa = VectorDBQA.from_chain_type(llm=llm, chain_type="stuff", vectorstore=doc_search,
                                    return_source_documents=True)
    result = qa({"query": query})
    return result


def query_online(url, query):
    llm = AzureChatOpenAI(openai_api_base=server_settings.azure_openai_endpoint,
                          openai_api_key=server_settings.azure_openai_key,
                          deployment_name=server_settings.azure_openai_model_name, temperature=0.7,
                          openai_api_version="2023-05-15")

    template = """在 >>> 和 <<< 之间是网页的返回的HTML内容。
    
    >>> {requests_result} <<<
    
    请回答以下问题:
    """

    template += query
    prompt = PromptTemplate(
        input_variables=["requests_result"],
        template=template
    )

    chain = LLMRequestsChain(llm_chain=LLMChain(llm=llm, prompt=prompt))
    inputs = {
        "url": url
    }

    response = chain(inputs)
    return response['output']


def chat_online(query):
    llm = AzureChatOpenAI(openai_api_base=server_settings.azure_openai_endpoint,
                          openai_api_key=server_settings.azure_openai_key,
                          deployment_name=server_settings.azure_openai_model_name, temperature=0.7,
                          openai_api_version="2023-05-15")
    search = BingSearchAPIWrapper(bing_subscription_key=server_settings.bing_search_key,
                                  bing_search_url=server_settings.bing_search_url)
    tools = [
        Tool.from_function(
            func=search.run,
            name="Search",
            description="useful for when you need to answer questions about current events"
        ),
    ]

    PREFIX = '''You are an AI data scientist. 
    You have done years of research in studying all the AI algorthims. 
    You also love to write.
     On free time you write blog post for articulating what you have learned about different AI algorithms.
      Do not forget to include information on the algorithm's benefits, disadvantages, and applications.
       Additionally, the blog post should explain how the algorithm advances model reasoning by a whopping 70% and how it is a plug in and play version,
        connecting seamlessly to other components.
    '''

    FORMAT_INSTRUCTIONS = """To use a tool, please use the following format:
    '''
    Thought: Do I need to use a tool? Yes
    Action: the action to take, should be one of [{tool_names}]
    Action Input: the input to the action
    Observation: the result of the action
    '''

    When you have gathered all the information regarding AI algorithm, just write it to the user in the form of a blog post.

    '''
    Thought: Do I need to use a tool? No
    AI: [write a blog post]
    '''
    """

    SUFFIX = '''

    Begin!

    Previous conversation history:
    {chat_history}

    Instructions: {input}
    {agent_scratchpad}
    '''
    agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True,
                             prefix=PREFIX,
                             suffix=SUFFIX,
                             format_instructions=FORMAT_INSTRUCTIONS
                             )
    return agent.run(query)