# Copyright (c) 2024.
# -*-coding:utf-8 -*-
"""
@file: reserve.py
@author: Jerry(Ruihuang)Yang
@email: rxy216@case.edu
@time: 12/16/24 21:09
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import requests
import time
from datetime import datetime
import pytz
import json


class AnimateCafeBot:
    def __init__(self, desired_dates, fair_code, full_fair_code, cafe_title, headless=True):
        self.desired_dates = desired_dates
        self.fair_code = fair_code
        self.full_fair_code = full_fair_code
        self.cafe_title = cafe_title
        # Initialize the driver manager
        driver_manager = ChromeDriverManager()

        # Get the driver path (this uses cache if available)
        driver_path = driver_manager.install()
        print(f"ChromeDriver path: {driver_path}")

        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')

        self.driver = webdriver.Chrome(
            service=Service(driver_path),
            options=options)
        self.wait = WebDriverWait(self.driver, 10)

    def wait_and_click(self, by, value):
        element = self.wait.until(EC.element_to_be_clickable((by, value)))
        element.click()
        time.sleep(4)  # Additional wait to ensure page loads

    def wait_for_queue(self):
        while True:
            try:
                # Check for queue message
                queue_text = self.driver.find_element(By.XPATH, "//div[contains(text(), '順番待ちに追加されました')]")
                if queue_text:
                    print("In queue... waiting 5 seconds")
                    time.sleep(5)
                    continue
            except:
                # If we can't find the queue text, check if we're on the main page
                try:
                    self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'btn-primary')))
                    print("Queue completed, proceeding...")
                    return
                except:
                    print("In queue... waiting 5 seconds")
                    time.sleep(5)
                    continue

    def login(self, email, password):
        # Go to the main page
        self.driver.get('https://reserve2.animatecafe.jp/reserve/')

        # Wait for queue to complete
        self.wait_for_queue()

        # Click the first login button
        self.wait_and_click(By.CLASS_NAME, 'btn-primary')

        # Click the Club Animate login button
        self.wait_and_click(By.CLASS_NAME, 'btn-clubanimate')

        # Input email and password
        email_input = self.wait.until(EC.presence_of_element_located((By.ID, 'CustomerMailAddress')))
        email_input.send_keys(email)

        password_input = self.wait.until(EC.presence_of_element_located((By.ID, 'CustomerPassword')))
        password_input.send_keys(password)

        # Click login button
        self.wait_and_click(By.CLASS_NAME, 'login_button')

        # Wait for Oauth callback loading, make sure this "/auth/callback/clubanimate" is not in the URL\
        # or ANIMATECAFE-NGR not in cookies
        while "/auth/callback/clubanimate" in self.driver.current_url and not any(
                cookie['name'] == 'ANIMATECAFE-NGR' for cookie in self.driver.get_cookies()):
            print("Waiting for Oauth callback...")
            time.sleep(25)
            # refresh the page
            self.driver.refresh()

        # navigate to the reservation page https://reserve.animatecafe.jp/
        self.driver.get('https://reserve.animatecafe.jp')

        # Click on the reservation button after login
        self.wait_and_click(By.CLASS_NAME, 'btn-cafereserve')

    def navigate_to_reservation(self):
        # Find the specific div containing cafe title and click its reserve button
        ensemble_stars_xpath = f"//div[contains(@class, 'card-body')]//div[contains(text(), '{self.cafe_title}')]/ancestor::div[contains(@class, 'card-body')]//button[contains(@class, 'btn-reserve')]"
        self.wait_and_click(By.XPATH, ensemble_stars_xpath)

        # Click the first reserve button on the next page
        self.wait_and_click(By.CLASS_NAME, 'btn-reserve')

    def check_and_ensure_login(self, email, password):
        # Get all cookies
        cookies = self.driver.get_cookies()

        # Check if the required cookie exists
        has_required_cookie = any(cookie['name'] == 'ANIMATECAFE-NGR' for cookie in cookies)

        if not has_required_cookie:
            print("Required cookie not found. Performing relogin...")
            self.login(email, password)
            return self.check_and_ensure_login(email, password)  # Recursive check to ensure login succeeded

        print("Required cookie found, proceeding...")
        return True

    def get_fair_data(self, email, password):
        # Check login status before making request
        if not self.check_and_ensure_login(email, password):
            raise Exception("Failed to maintain login session")

        # Get cookies from Selenium session
        selenium_cookies = self.driver.get_cookies()

        # Convert Selenium cookies to requests format
        cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}

        # Make the GET request
        response = requests.get(
            f'https://api.animatecafe.jp/api/reserve/fair/{self.fair_code}/group/{self.full_fair_code}',
            cookies=cookies
        )

        return response.json()

    def check_seat_availability(self, response_data):
        """
        Check if seats are available in the reservation list and if the time slot is still valid
        Args:
            response_data (dict): The API response data containing reservation information
        """
        # Set up Japan timezone
        japan_tz = pytz.timezone('Asia/Tokyo')
        current_time = datetime.now(japan_tz)

        print(f"Current time: {current_time.strftime('%Y-%m-%d %H:%M')} JST")

        if 'reserve_list' not in response_data:
            print("No reservation list found in data")
            return

        reservation_success = False
        for reservation in response_data['reserve_list']:
            current_seats = reservation.get('seats', 0)
            total_seats = reservation.get('total_seats', 0)

            # First check if seats are available
            if total_seats > current_seats:
                # Parse the date and time
                date_str = reservation.get('reserve_date', '')
                time_str = reservation.get('reserve_date_start_time', '')

                try:
                    # Parse the base date
                    base_date = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                    date_only = base_date.strftime('%Y-%m-%d')

                    # Check if date is in desired dates
                    if date_only not in self.desired_dates:
                        print(f"Seats available but not on desired date: {date_only} {time_str}")
                        print("---")
                        continue

                    # Parse the time
                    time_parts = datetime.strptime(time_str, '%H:%M').time()
                    # Combine date and time
                    reservation_datetime = japan_tz.localize(
                        datetime.combine(base_date.date(), time_parts)
                    )

                    if reservation_datetime > current_time:
                        print(f"Valid seats available!")
                        print(f"Time slot: {reservation.get('reserve_date_name', 'Unknown')}")
                        print(f"Available seats: {total_seats - current_seats}")
                        print(f"Store: {reservation.get('store_name', 'Unknown')}")
                        print(f"Start time: {reservation_datetime.strftime('%Y-%m-%d %H:%M')} JST")
                        print("---")
                        # actual reservation
                        reservation_details = self.make_reservation(self.driver, reservation)
                        if reservation_details.get('reserve_number', False):
                            reservation_success = True
                            break
                    else:
                        print(
                            f"Seats available but time slot has passed: {reservation.get('reserve_date_name', 'Unknown')}")
                        print("---")
                except Exception as e:
                    print(f"Error reserving: {e}")
                    print(f"Raw date: {date_str}, Raw time: {time_str}")
                    print("---")
            else:
                pass

        if reservation_success:
            print("Reservation successful!!!!!!!!!!!!!")
            return True

        return False

    def make_reservation(self, driver, available_slot):
        """
        Make a reservation using the provided slot information
        Args:
            driver: Selenium WebDriver instance for getting cookies and session info
            available_slot: Dictionary containing the reservation slot information
        Returns:
            dict: Reservation details
        """
        return_dict = {}
        # Get cookies from current session
        selenium_cookies = driver.get_cookies()
        cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
        csrf_token = cookies.get('_csrf')

        # Get user_id from session storage
        user_data = driver.execute_script("return window.sessionStorage.getItem('animatecafe-reserve');")
        user_id = None
        if user_data:
            try:
                user_info = json.loads(user_data)
                user_id = user_info['user']['user_id']
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Failed to get user_id from session storage: {e}")

        if not user_id:
            raise Exception("User ID not found in session storage")

        # Step 1: Initial reservation request
        payload = {
            "fair_code": available_slot['reserve_group_code'].split('_')[0],
            "fair_id": available_slot['fair_id'],
            "group_id": available_slot['group_id'],
            "reserve_count": 2,
            "reserve_date_id": available_slot['reserve_date_id'],
            "user_id": user_id
        }

        print("Making initial reservation request...")
        print(f"Payload: {payload}")
        response = requests.post(
            'https://api.animatecafe.jp/api/reserve/store',
            json=payload,
            cookies=cookies,
            headers={'Content-Type': 'application/json', 'X-Csrf-Token': csrf_token}
        )

        if response.status_code != 200:
            raise Exception(f"Initial reservation failed: {response.text}")

        access_key = response.json().get('access_key')
        if not access_key:
            raise Exception("No access key received")

        print(f"Received access key: {access_key}")

        # Step 2: Check reservation process
        attempts = 0
        max_attempts = 10
        job_status = None
        reserve_id = None

        while attempts < max_attempts:
            print(f"Checking reservation status (attempt {attempts + 1}/{max_attempts})...")
            check_response = requests.post(
                'https://api.animatecafe.jp/api/reserve/reserve_process_check',
                json={"access_key": access_key},
                cookies=cookies,
                headers={'Content-Type': 'application/json', 'X-Csrf-Token': csrf_token}
            )

            if check_response.status_code != 200:
                raise Exception(f"Status check failed: {check_response.text}")

            check_data = check_response.json()
            job_status = check_data.get('job_status')
            reserve_id = check_data.get('reserve_id')

            if job_status == "1" and reserve_id:
                print("Reservation process completed!")
                # This is to make sure even if step 3 fails, we do not reserve again
                return_dict['reserve_number'] = reserve_id
                break

            attempts += 1
            time.sleep(2)

        if job_status != "1" or not reserve_id:
            raise Exception("Failed to complete reservation process after maximum attempts")

        # Step 3: Get reservation details
        print("Fetching reservation details...")
        details_response = requests.post(
            'https://api.animatecafe.jp/api/historyreserve/detail',
            json={"reserve_id": str(reserve_id)},
            cookies=cookies,
            headers={'Content-Type': 'application/json', 'X-Csrf-Token': csrf_token}
        )

        if details_response.status_code != 200:
            raise Exception(f"Failed to get reservation details: {details_response.text}")

        print("Reservation details received!")
        print(f"Details: {details_response.json()}")
        return_dict = details_response.json()
        return return_dict

    def close(self):
        self.driver.quit()


def main():
    # Replace with your credentials
    email = "xxx@example.com"
    password = "example_password"
    # Define desired dates
    desired_dates = ['2024-12-24', '2024-12-26', '2024-12-27']
    # Define fair code and group ID
    fair_code = 'ac000000'
    full_fair_code = f'{fair_code}_000_0'
    # Define cafe title
    cafe_title = 'あんさんぶるスターズ！！'
    # check every x seconds
    check_interval = 5
    # max attempts
    max_attempts = 1000

    try:
        bot = AnimateCafeBot(desired_dates, fair_code, full_fair_code, cafe_title, headless=False)  # Set headless to True for no GUI
        bot.login(email, password)
        bot.navigate_to_reservation()
        for i in range(max_attempts):
            print(f"Checking seat availability attempt {i + 1}")
            fair_data = bot.get_fair_data(email, password)
            if bot.check_seat_availability(fair_data):
                print("Seat Reserved!")
                break
            else:
                print(f"No seats available, waiting {check_interval} seconds before checking again")
                time.sleep(check_interval)  # Wait some seconds before checking again
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        bot.close()


if __name__ == "__main__":
    main()
