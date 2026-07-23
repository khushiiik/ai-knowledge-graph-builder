from io import BytesIO
from fastapi.datastructures import UploadFile
from app.validators.upload_validator import validate_uploaded_file


def test_batch_upload_validation():
    # Test valid text file
    f1 = UploadFile(
        filename="test1.txt",
        file=BytesIO(b"Hello world file 1"),
        headers={"content-type": "text/plain"},
    )
    # Test valid json file
    f2 = UploadFile(
        filename="test2.json",
        file=BytesIO(b'{"key": "value"}'),
        headers={"content-type": "application/json"},
    )

    validate_uploaded_file(f1)
    validate_uploaded_file(f2)
    print("ALL BATCH UPLOAD VALIDATION TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_batch_upload_validation()
