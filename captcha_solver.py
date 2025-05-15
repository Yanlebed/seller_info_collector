import asyncio
import logging
import base64
import json
import os
import time
from typing import Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


class CaptchaSolver:
    """Class to handle CAPTCHA solving using Capsolver service"""

    def __init__(self, api_key: str, max_retries: int = 3, retry_delay: float = 5.0):
        """
        Initialize CAPTCHA solver

        Args:
            api_key: Capsolver API key
            max_retries: Maximum number of retries for checking solution
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.api_url = "https://api.capsolver.com/createTask"
        self.get_result_url = "https://api.capsolver.com/getTaskResult"

    async def solve_image_captcha(self, image_path: str) -> Optional[str]:
        """
        Solve image CAPTCHA

        Args:
            image_path: Path to the CAPTCHA image file

        Returns:
            Solved CAPTCHA text or None if failed
        """
        try:
            # Check if file exists
            if not os.path.exists(image_path):
                logger.error(f"CAPTCHA image not found: {image_path}")
                return None

            # Read and encode image
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

            # Send CAPTCHA to Capsolver
            task_id = await self._send_captcha(encoded_string)
            if not task_id:
                logger.error("Failed to send CAPTCHA to solver")
                return None

            # Get CAPTCHA solution
            solution = await self._get_captcha_solution(task_id)
            return solution

        except Exception as e:
            logger.error(f"Error solving image CAPTCHA: {str(e)}")
            return None

    async def _send_captcha(self, base64_image: str) -> Optional[str]:
        """
        Send CAPTCHA to Capsolver

        Args:
            base64_image: Base64 encoded image

        Returns:
            Task ID for checking solution or None if failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Format request for Capsolver
                payload = {
                    "clientKey": self.api_key,
                    "task": {
                        "type": "ImageToTextTask",
                        "body": base64_image,
                    }
                }

                async with session.post(self.api_url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Error sending CAPTCHA: HTTP {response.status}")
                        return None

                    try:
                        result = await response.json()
                        if result.get('errorId') == 0:
                            return result.get('taskId')
                        else:
                            logger.error(f"Error sending CAPTCHA: {result.get('errorDescription')}")
                            return None
                    except json.JSONDecodeError:
                        text = await response.text()
                        logger.error(f"Invalid JSON response: {text}")
                        return None

        except Exception as e:
            logger.error(f"Error sending CAPTCHA to solver: {str(e)}")
            return None

    async def _get_captcha_solution(self, task_id: str) -> Optional[str]:
        """
        Get CAPTCHA solution from Capsolver

        Args:
            task_id: Task ID from _send_captcha

        Returns:
            CAPTCHA solution text or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                # Wait before first check (Capsolver usually takes a few seconds to solve)
                await asyncio.sleep(5 if attempt == 0 else self.retry_delay)

                async with aiohttp.ClientSession() as session:
                    payload = {
                        "clientKey": self.api_key,
                        "taskId": task_id
                    }

                    async with session.post(self.get_result_url, json=payload) as response:
                        if response.status != 200:
                            logger.error(f"Error getting CAPTCHA solution: HTTP {response.status}")
                            continue

                        try:
                            result = await response.json()
                            if result.get('errorId') == 0:
                                status = result.get('status')
                                if status == 'ready':
                                    # Return the text from the solution object
                                    return result.get('solution', {}).get('text')
                                elif status == 'processing':
                                    logger.info(f"CAPTCHA still processing, retrying in {self.retry_delay} seconds")
                                    continue
                                else:
                                    logger.error(f"Unexpected status: {status}")
                                    return None
                            else:
                                logger.error(f"Error getting CAPTCHA solution: {result.get('errorDescription')}")
                                return None
                        except json.JSONDecodeError:
                            text = await response.text()
                            logger.error(f"Invalid JSON response: {text}")
                            continue

            except Exception as e:
                logger.error(f"Error getting CAPTCHA solution: {str(e)}")
                continue

        logger.error(f"Failed to get CAPTCHA solution after {self.max_retries} attempts")
        return None

    async def solve_amazon_captcha(self, page) -> Tuple[bool, str]:
        """
        Solve Amazon CAPTCHA directly from page

        Args:
            page: Playwright page object

        Returns:
            Tuple of (success, message)
        """
        try:
            # Check for captcha image
            captcha_img = await page.query_selector("//img[contains(@src, 'captcha')]")
            if not captcha_img:
                return False, "CAPTCHA image not found"

            # Take screenshot of the captcha
            timestamp = str(int(time.time()))
            screenshot_path = os.path.join("screenshots", f"captcha_{timestamp}.png")
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)

            await captcha_img.screenshot(path=screenshot_path)
            logger.info(f"CAPTCHA screenshot saved to: {screenshot_path}")

            # Solve the captcha
            solution = await self.solve_image_captcha(screenshot_path)
            if not solution:
                return False, "Failed to solve CAPTCHA"

            logger.info(f"CAPTCHA solution: {solution}")

            # Find the captcha input field
            captcha_input = await page.query_selector("//input[@id='captchacharacters']")
            if not captcha_input:
                return False, "CAPTCHA input field not found"

            # Type solution
            await captcha_input.fill("")  # Clear field first
            await page.keyboard.type(solution, delay=100)  # Type with delay to look human

            # Find and click submit button
            submit_button = await page.query_selector("//button[contains(@class, 'a-button-primary')]")
            if not submit_button:
                submit_button = await page.query_selector("//input[@type='submit']")

            if not submit_button:
                return False, "CAPTCHA submit button not found"

            # Click submit
            await submit_button.click()

            # Wait for page to load
            await page.wait_for_load_state("networkidle")

            # Check if CAPTCHA is still present
            captcha_still_present = await page.query_selector("//img[contains(@src, 'captcha')]")
            if captcha_still_present:
                return False, "CAPTCHA still present after submission, solution likely incorrect"

            return True, "CAPTCHA solved successfully"

        except Exception as e:
            logger.error(f"Error solving Amazon CAPTCHA: {str(e)}")
            return False, f"Error: {str(e)}"