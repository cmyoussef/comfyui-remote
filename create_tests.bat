@echo off
echo Creating tests folder structure...
echo.

REM Create all directories
echo Creating directories...
mkdir tests 2>nul
mkdir tests\utils 2>nul
mkdir tests\resources 2>nul
mkdir tests\resources\workflows 2>nul
mkdir tests\steps 2>nul
mkdir tests\unit 2>nul

REM Create empty files in tests root
echo Creating root files...
type nul > tests\pytest.ini
type nul > tests\__init__.py

REM Create empty files in utils
echo Creating utils files...
type nul > tests\utils\__init__.py
type nul > tests\utils\bootstrap.py

REM Create empty workflow files
echo Creating workflow files...
type nul > tests\resources\workflows\txt2img.json
type nul > tests\resources\workflows\img2img.json
type nul > tests\resources\workflows\zdepth.json

REM Create empty step test files
echo Creating step test files...
type nul > tests\steps\test_01_server.py
type nul > tests\steps\test_02_connect_ws.py
type nul > tests\steps\test_03_post_prompt.py
type nul > tests\steps\test_04_load_workflow.py
type nul > tests\steps\test_05_update_params.py
type nul > tests\steps\test_06_compile_payload.py
type nul > tests\steps\test_07_submit_local.py
type nul > tests\steps\test_08_remote_executor.py
type nul > tests\steps\test_09_workflow_manager_local.py
type nul > tests\steps\test_10_cli_and_validate.py

REM Create empty unit test files
echo Creating unit test files...
type nul > tests\unit\test_00_graph_compiler.py
type nul > tests\unit\test_01_rest_client.py
type nul > tests\unit\test_02_ws_client.py
type nul > tests\unit\test_03_connector_flow.py
type nul > tests\unit\test_04_workflow_loader_params.py
type nul > tests\unit\test_05_validation_output_handler.py

echo.
echo Done! All files and folders created successfully.
echo.
echo Folder structure:
tree /F tests

pause