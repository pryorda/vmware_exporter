# Custom CA certificates

Add your existing CA certificates encoded as PEM-certificates into this directory. They will be added to the trusted root certificates of the alpine linux base system and respected by the underlying python library used to connect to your VirtualCenter server.

## PEM encoded certificates
A PEM-encoded certificate file starts with 

`-----BEGIN CERTIFICATE-----`

end ends with 

`-----END CERTIFICATE-----`

## Usage
Store your custom root CA certificate into the `certs` folder. If you have a certificate chain, you will need to split the chain and store each certificate as a seperate file. 

During `docker build` all files will be copied to `/usr/local/share/ca-certificates` and the command `update-ca-certificates` appends all certificates to the trusted root CA collection found at `/etc/ssl/certs/ca-certificates.crt`.

`update-ca-certificates` will ignore files containing more than one certificate, which is the reason for splitting chains into individual files.

## Certificate chain example
**Note:** The certificates will be deployed using `update-ca-certicates`. During this step, the file extension `.pem` will be added to all files. To avoid a duplicate `.pem.pem` file extension, the exemplary filenames shown below have been stripped from a file extension altogether. You can name the files to your liking, of course.

### root CA certificate
**Filename:** `YOUR_ORG-root`[.pem]

**Contents:**
```
-----BEGIN CERTIFICATE-----
BQAwgYwxCzAJBgNVBAYTAkRFMRswGQYDVQQIExJCYWRlbi1XdWVydHRlbWJlcmcx
...
2uvOgYT/kkhCBM2fKS0domiDJE5iRrKzGOOQoh82Ya2P2epK6oHnaj6Zn+18o4k2
-----END CERTIFICATE-----
```

### Intermediate CA certificate
**Filename:** `YOUR_ORG-intermediate`[.pem]

**Contents:**
```
-----BEGIN CERTIFICATE-----
cnQxEjAQBgNVBAoTCXNod2lsbC5pbzEUMBIGA1UECxMLQ0EgU2VydmljZXMxIjAg
...
+L9xUQZlXZeEyGmtwY5dyckDuRcUCYUZQAjR0MhSR4wZaCYyc+gnv6Mc6kJS6bCz
-----END CERTIFICATE-----
```