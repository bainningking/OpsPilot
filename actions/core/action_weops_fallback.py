from typing import Any, Text, Dict, List

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma
from rasa_sdk import Action, Tracker, logger
from rasa_sdk.events import UserUtteranceReverted
from rasa_sdk.executor import CollectingDispatcher

from actions.constant.server_settings import server_settings
from actions.utils.azure_utils import query_chatgpt
from actions.utils.langchain_utils import langchain_qa


class ActionWeOpsFallback(Action):

    def __init__(self) -> None:
        super().__init__()
        if server_settings.vec_db_path is not None:
            embeddings = HuggingFaceEmbeddings(model_name='shibing624/text2vec-base-chinese',
                                               cache_folder='cache/models',
                                               encode_kwargs={
                                                   'show_progress_bar': True
                                               })
            self.doc_search = Chroma(persist_directory=server_settings.vec_db_path, embedding_function=embeddings)

    def name(self) -> Text:
        return "action_weops_fallback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_msg = tracker.latest_message['text']
        system_prompt = server_settings.fallback_prompt
        run_mode = server_settings.run_mode

        logger.info(f'无法识别用户的意图，进入默认Fallback，用户输入的信息为:{user_msg}')
        logger.info(f'TOP3 Intent结果如下：{tracker.latest_message["intent_ranking"][0:3]}')
        if tracker.active_loop_name is None:
            if run_mode == 'DEV':
                dispatcher.utter_message(text='OpsPilot当前运行在开发模式，没有办法回复这些复杂的问题哦')
                return [UserUtteranceReverted()]
            else:
                try:
                    if server_settings.azure_openai_endpoint is None:
                        dispatcher.utter_message(text='WeOps智能助理联网检索能力没有打开,无法回答这个问题.')
                        return [UserUtteranceReverted()]

                    events = list(filter(lambda x: x.get("event") == "user" and x.get("text"), tracker.events))
                    user_messages = []
                    for event in reversed(events):
                        if len(user_messages) >= 10:
                            break
                        user_messages.insert(0, event.get("text"))

                    if server_settings.fallback_chat_mode == 'knowledgebase':
                        result = langchain_qa(self.doc_search, user_msg)
                        logger.info(result)
                        dispatcher.utter_message(text=result['result'])
                    else:
                        user_prompt = ''
                        for user_message in user_messages:
                            user_prompt += user_message + '\n'
                        user_prompt += user_msg

                        if user_prompt != '':
                            result = query_chatgpt(system_prompt, user_prompt)
                        logger.info(result)
                        dispatcher.utter_message(text=result)
                except Exception as e:
                    logger.exception('请求Azure OpenAI 服务异常')
                    dispatcher.utter_message(text='WeOps智能助理处于非常繁忙的状态，请稍后再试.')
                return [UserUtteranceReverted()]
        else:
            return []
