from logging import Handler
import os
import html
import requests

class TelegramSendLogHandler(Handler):
    def __init__(self, token=None, chat_id_list=[], *args, **kwargs):
        Handler.__init__(self, *args, **kwargs)
        if not chat_id_list:
            chat_id_list = [int(os.environ.get('REPORT_CHAT_ID', '95604679'))]
        self.token = token
        self.chat_id_list = chat_id_list
        if type(chat_id_list) is not list:
            self.chat_id_list = [chat_id_list]
        
    def emit(self, record):
        try:
            for chat_id in self.chat_id_list:
                try:
                    msg = self.format(record)
                    requests.post('https://api.telegram.org/bot{}/sendMessage'.format(self.token), 
                                  data={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'})
                except Exception as e:
                    print(f"Error sending log to Telegram: {e}")
                    print("Bot Not Defined")

        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)
