[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/Fvxb6Q3O)
Smile App Starter Code - includes tests

Requirements.txt is updated on July 2024

Includes all tests (unittest, pytest, selenium)

Name: Tran Minh Duc Nguyen
Major: Computer Science

------------------------
## Running the application
-----------------------

### To run this example:
- Start the application with the following command:
    ```
    python smile.py
    ```

### To run the tests:
- run the tests for Model (unittest)
    ``` 
    python -m unittest -v tests/test_models.py 
    ```
- run the tests for routes (pytest)
    ```
    python -m pytest -v tests/test_routes.py
    ```
- run the selenium tests
    * Download the Chrome webdriver for your Chrome browser version (https://chromedriver.chromium.org/downloads); extract and copy it under `C:\Webdriver` folder.
    * Run the SmileApp in a terminal window: 
        ```
        python smile.py
        ```
    * Run the selenium tests
    ```
        python tests/test_selenium.py
    ```