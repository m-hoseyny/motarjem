import re
import asyncio
import aiohttp
import datetime
import srt
import logging
import json
from logger_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)


def count_words_in_srt(srt_content):
    """
    Count the number of words in an SRT file using the srt library.

    Args:
        srt_content (str): srt content

    Returns:
        int: Number of words in the SRT file
    """
    try:
        
       
        # Parse the SRT content
        subtitles = list(srt.parse(srt_content))
        
        # Combine all subtitle content and count words
        all_text = ' '.join(subtitle.content for subtitle in subtitles)
        words = re.findall(r'\w+', all_text)
        return len(words)
        
    except FileNotFoundError:
        logger.error(f"Error: File '{srt_file_path}' not found.")
        return -1
    except srt.SRTParseError:
        logger.error(f"Error: Invalid SRT file format in '{srt_file_path}'")
        return -1
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return -1

class SubtitleTranslator:
    def __init__(self, api_key, batch_size=10, base_url='https://api.morshed.pish.run/v1'):
        self.api_key = api_key
        self.base_url = base_url
        self.batch_size = batch_size
        self.delimiter = '[DELIMITER]'
        self.total_price = 0
        self.total_lines = 0
        self.total_words = 0
        self.total_tokens = 0
        
    def calculate_cost_toman(self, unit_price):
        """Calculate cost in Toman"""
        return self.total_words * unit_price

    async def parse_srt_content(self, content):
        """Parse SRT content from string"""
        try:
            return list(srt.parse(content))
        except Exception as e:
            logger.error(f"Error parsing SRT content: {str(e)}")
            raise

    async def translate_batch(self, texts, retries=3):
        """Translate a batch of subtitle texts"""
        try:
            logger.debug(f"Translating batch of {len(texts)} subtitles")
            
            # Join texts with delimiter
            query = f"\n{self.delimiter}\n".join(texts)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "inputs": {},
                "query": query,
                "response_mode": "blocking",
                "conversation_id": "",
                "user": "MotarjemAI",
                "files": []
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat-messages",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API request failed with status {response.status}: {error_text}")
                        raise Exception(f"API request failed with status {response.status}")
                    
                    data = await response.json()
                    if "answer" not in data:
                        logger.error(f"Invalid API response: {data}")
                        raise Exception("Invalid API response")
                    
                    # Get translations
                    translations = data["answer"].split(f"{self.delimiter}")
                    translations = [t.strip().replace('<output>', '').replace('</output>', '') for t in translations]
                    
                    # Update total price
                    if "metadata" in data and "usage" in data["metadata"]:
                        self.total_price += float(data["metadata"]["usage"]["total_price"])
                        self.total_tokens += int(data["metadata"]["usage"]["total_tokens"])
                        logger.debug(f"Batch translation completed. Total cost so far: ${self.total_price:.4f}")
                    
                    return translations

        except Exception as e:
            logger.error(f"Error in translation batch: {str(e)}, retries={retries}")
            if retries == 0:
                return ["" for _ in texts]
            return await self.translate_batch(texts, retries=retries - 1)

    async def translate_all_subtitles(self, subtitles, progress_callback=None):
        """Translate all subtitles with progress updates"""
        translated_subtitles = []
        batch_texts = []
        batches_subs = []
        total_batches = (len(subtitles) + self.batch_size - 1) // self.batch_size
        await progress_callback(0)
        for i, subtitle in enumerate(subtitles):
            batch_texts.append(subtitle.content)
            batches_subs.append(subtitle)

            if len(batch_texts) == self.batch_size or i == len(subtitles) - 1:
                translations = await self.translate_batch(batch_texts)
                
                for parent_sub, translation in zip(batches_subs, translations):
                    translated_sub = srt.Subtitle(
                        index=parent_sub.index,
                        content=translation.strip(),
                        start=parent_sub.start,
                        end=parent_sub.end
                    )
                    translated_subtitles.append(translated_sub)
                
                # Calculate and report progress
                current_batch = (i + 1) // self.batch_size
                progress = (current_batch / total_batches) * 100
                if progress_callback:
                    await progress_callback(progress)
                
                batch_texts = []
                batches_subs = []
        self.total_words = count_words_in_srt(self.compose_srt(translated_subtitles))
        self.total_lines = len(translated_subtitles)
        return translated_subtitles

    def compose_srt(self, translated_subtitles):
        """Convert translated subtitles to string"""
        return srt.compose(translated_subtitles)
