"""Credential-free packaging check, run inside the dispatcher image/environment."""
import importlib.util
import json
import resource
import sys


def main():
    import service.app
    import service.execution
    import modal
    forbidden = ('numpy','pandas','radiomics','SimpleITK','pydicom','rt_utils','cv2')
    present = [name for name in forbidden if importlib.util.find_spec(name) is not None]
    if present or any(name.startswith('src.') for name in sys.modules):
        raise SystemExit('Dispatcher contains native/imaging dependencies')
    from fastapi.testclient import TestClient
    # Health has no database/provider calls and works without lifespan/creds.
    assert TestClient(service.app.app).get('/health').json() == {'status':'ok'}
    print(json.dumps({'native_dependencies':present,'modal_version':modal.__version__,
        'max_rss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'platform':sys.platform}))


if __name__ == '__main__':
    main()
