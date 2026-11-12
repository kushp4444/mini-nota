"""Bounded server-only S3/R2 artifacts. References are trusted persisted metadata.

The caller MUST authorize the run capability before using read/presign; a run ID
alone is not a capability. This module never accepts an object key from a browser.
"""
import hashlib
import os
import re
from botocore.exceptions import ClientError


class StorageError(ValueError):
    pass


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', value):
        raise StorageError('Unsafe storage identity')
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def client_from_env(role):
    """Separate credentials for ASSETS (read), UPLOAD (bootstrap), RESULTS (write/read)."""
    import boto3
    from botocore.config import Config
    prefix = f'R2_{role.upper()}_'
    return boto3.client('s3', endpoint_url=os.environ[prefix+'ENDPOINT_URL'], region_name='auto',
        aws_access_key_id=os.environ[prefix+'ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ[prefix+'SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4', retries={'max_attempts':3,'mode':'standard'},
                      connect_timeout=10, read_timeout=60, request_checksum_calculation='when_required',
                      response_checksum_validation='when_required'))


def missing(error):
    return isinstance(error, ClientError) and error.response['Error']['Code'] in ('404','NoSuchKey','NotFound')


def read_verified(client, bucket, key, size, checksum, *, max_bytes=None):
    if type(size) is not int or size < 0 or (max_bytes is not None and size > max_bytes):
        raise StorageError('Object exceeds allowed size')
    result = client.get_object(Bucket=bucket, Key=key)
    body = result['Body']
    try:
        if result['ContentLength'] != size:
            raise StorageError('Object size mismatch')
        data = body.read(size+1)
        if len(data) != size or sha(data) != checksum:
            raise StorageError('Object checksum or incomplete content mismatch')
        return data
    finally:
        body.close()


class ArtifactStore:
    MEDIA_TYPES = {'image/png','image/svg+xml','application/json','text/csv','application/octet-stream'}

    def __init__(self, client, bucket, prefix='runs', max_bytes=4_000_000):
        self.client, self.bucket = client, bucket
        self.prefix, self.max_bytes = token(prefix), max_bytes

    @classmethod
    def from_env(cls, role='results'):
        return cls(client_from_env(role), os.environ[f'R2_{role.upper()}_BUCKET'],
                   os.environ.get(f'R2_{role.upper()}_PREFIX','runs'))

    def _key(self, run_id, artifact_id):
        return f'{self.prefix}/{token(run_id)}/{token(artifact_id)}'

    def publish(self, run_id, artifact_id, data, media_type):
        key = self._key(run_id, artifact_id)
        if not isinstance(data, bytes) or len(data)>self.max_bytes or media_type not in self.MEDIA_TYPES:
            raise StorageError('Unsupported artifact type or size')
        ref = {'storage':'s3','run_id':run_id,'artifact_id':artifact_id,'key':key,
               'sha256':sha(data),'size_bytes':len(data),'media_type':media_type}
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=media_type,
                Metadata={'sha256':ref['sha256'],'run-id':run_id}, IfNoneMatch='*')
        except ClientError as error:
            if error.response['Error']['Code'] not in ('PreconditionFailed','ConditionalRequestConflict','412','409'):
                raise
        # GET, not ETag or uploader-controlled metadata, verifies a completed transfer
        # and makes a retry with different bytes fail without replacing the object.
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        if head.get('ContentType') != media_type:
            raise StorageError('Published artifact type conflict')
        self.read(run_id, ref)
        return ref

    def read(self, run_id, reference):
        if reference.get('storage')!='s3' or reference.get('run_id')!=run_id or reference.get('key')!=self._key(run_id,reference.get('artifact_id')):
            raise StorageError('Artifact does not belong to this run')
        if reference.get('media_type') not in self.MEDIA_TYPES:
            raise StorageError('Unsupported artifact type')
        return read_verified(self.client,self.bucket,reference['key'],reference['size_bytes'],reference['sha256'],max_bytes=self.max_bytes)

    def presign(self, run_id, reference, expires=60):
        """Optional fresh download URL; persist bytes, never the URL, in History."""
        if type(expires) is not int or not 1<=expires<=300:
            raise StorageError('Artifact URL lifetime must be 1–300 seconds')
        self.read(run_id,reference)
        return self.client.generate_presigned_url('get_object',Params={'Bucket':self.bucket,'Key':reference['key']},ExpiresIn=expires)
