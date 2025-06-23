import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="fusion-tools",
    version="3.6.17",
    author="Sam Border",
    author_email="sam.border2256@gmail.com",
    description="Modular visualization and analysis dashboard creation for high-resolution microscopy images",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/spborder/fusion-tools",
    python_requires=">=3.8",
    install_requires=[
        "lxml>=4.9.2",
        "geojson>=3.0.1",
        "shapely>=2.0.1",
        "anndata",
        "geopandas>=1.0.1",
        "girder-client",
        "numpy>=1.20.0",
        "large-image[common]",
        "requests",
        "uuid>=1.30",
        "scikit-image",
        "umap-learn>=0.5.6",
        "statsmodels>=0.14.0",
        "typing-extensions>=4.8.0",
        "girder-job-sequence>=0.2.7",
        "SQLAlchemy>=2.0.0"
    ],
    extras_require = {
        'interactive': [
            "dash-leaflet[all]>=1.0.15",
            "dash>=2.18.1,<3.0.0",
            "dash-extensions>=1.0.18",
            "dash-uploader==0.7.0-a1",
            "dash_mantine_components>=0.14.4",
            "dash-bootstrap-components>=1.6.0",
            "dash_treeview_antd>=0.0.1",
            "fastapi>=0.103.2",
            "uvicorn>=0.30.6",
            "python-multipart"
        ]
    },
    packages=setuptools.find_packages(where = 'src',include=["fusion_tools*"]),
    package_dir={"":"src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)