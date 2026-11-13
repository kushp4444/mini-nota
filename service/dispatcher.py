"""Render entrypoint. No private engine and no local compute fallback."""
import os


def main():
    if os.environ.get('EXECUTION_BACKEND') != 'modal':
        raise SystemExit('Render dispatcher requires EXECUTION_BACKEND=modal')
    required = ('RUN_DATABASE_URL','CHECKPOINT_SIGNING_KEY','MODAL_APP_NAME',
                'MODAL_TOKEN_ID','MODAL_TOKEN_SECRET','R2_RESULTS_ENDPOINT_URL',
                'R2_RESULTS_BUCKET','R2_RESULTS_ACCESS_KEY_ID','R2_RESULTS_SECRET_ACCESS_KEY')
    if any(not os.environ.get(key) for key in required) or not (os.environ.get('CATALOG_DATABASE_URL') or os.environ.get('DATABASE_URL')):
        raise SystemExit('Configure required dispatcher database, Modal, signing and result-reader settings')
    if os.environ.get('LOCAL_ARTIFACT_DIR'):
        raise SystemExit('Render requires durable object storage')
    import uvicorn
    uvicorn.run('service.app:app',host='0.0.0.0',port=int(os.environ.get('PORT','8000')),workers=1,access_log=False)


if __name__ == '__main__':
    main()
