# Change Log
All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/) and [Keep a changelog](https://github.com/olivierlacan/keep-a-changelog).

 <!--next-version-placeholder-->

## v0.18.1 (2021-09-26)
### Fix
* **fix_tag:** Adding dhub automation - fix tag ([#292](https://github.com/pryorda/vmware_exporter/issues/292)) ([`c3d7830`](https://github.com/pryorda/vmware_exporter/commit/c3d7830ea92567c21b5e5db51ead6ad3983c4082))

## v0.18.0 (2021-09-26)
### Feature
* **adding_dhub_automation:** Adding dhub automation ([#291](https://github.com/pryorda/vmware_exporter/issues/291)) ([`ba56f30`](https://github.com/pryorda/vmware_exporter/commit/ba56f300d1d2c2e7439e1f3406aada1e0111ed34))

## v0.17.1 (2021-08-19)
### Fix
* **adding_version:** Adding version cli ([`f83b058`](https://github.com/pryorda/vmware_exporter/commit/f83b0580f58bc2d3c7d53f99194d03ef02a02758))

## v0.17.0 (2021-08-19)
### Feature
* **add_vm_ds:** Adding vm datastore.  ([`16c8604`](https://github.com/pryorda/vmware_exporter/commit/16c8604ef4e6c77d1eb5f1876ead544fde540967))

## v0.16.1 (2021-06-10)
### Fix
* **fixing_sensor:** Fix for badly behaving super-micro sensor #271 ([`2d5c196`](https://github.com/pryorda/vmware_exporter/commit/2d5c1965ec21ee6afc1d9ff3063bea3ca93bd99d))

## v0.16.0 (2021-03-30)
### Feature
* **adding_signature_validation:** Adding Validation for signatures.  ([`72430d9`](https://github.com/pryorda/vmware_exporter/commit/72430d91f181b17c977aecb9b1fda90ef83bd4ee))

## v0.15.1 (2021-03-30)
### Fix
* **fix_sensor_lookup:** Fixing sensor lookup ([#262](https://github.com/pryorda/vmware_exporter/issues/262)) ([`e97c855`](https://github.com/pryorda/vmware_exporter/commit/e97c855581a4e8db8804c542aaece62b3d85081b))

## v0.15.0 (2021-03-29)
### Feature
* **sensors:** Adding sensor metrics ([`da2f489`](https://github.com/pryorda/vmware_exporter/commit/da2f48929fc8e377202c4e193d2d4836e4d90a38))

## v0.14.3 (2021-03-11)
### Fix
* **optimize_build:** Remove travis, add ifs to action ([#254](https://github.com/pryorda/vmware_exporter/issues/254)) ([`43d6556`](https://github.com/pryorda/vmware_exporter/commit/43d6556556171b3ada6804a29aaff4710e511094))

## [0.4.2] - 2018-01-02
## Fixed
- [#60](https://github.com/pryorda/vmware_exporter/pull/60) Typo Fix


## [0.4.1] - 2018-01-02
## Changed
- [#50](https://github.com/pryorda/vmware_exporter/pull/50) Added tests + CI (#47) (#50)
- [#55](https://github.com/pryorda/vmware_exporter/pull/55) Robustness around collected properties #55
- [#58](https://github.com/pryorda/vmware_exporter/pull/58) Multiple section support via ENV variables. #58

## [0.4.0] - 2018-12-28
## Changed
- [#44](https://github.com/pryorda/vmware_exporter/pull/44) Embrace more twisted machinery + allow concurrent scrapes

## [0.3.1] - 2018-12-23
### Changed
- [#43](https://github.com/pryorda/vmware_exporter/pull/43) Property collectors
### Fixed
- [#40](https://github.com/pryorda/vmware_exporter/pull/40) Fixed race condition with intermittent results @Jc2k

## [0.3.0] - 2018-12-09
### Changed
- [#35](https://github.com/pryorda/vmware_exporter/pull/35) Refactor threading @Jc2k
- [#34](https://github.com/pryorda/vmware_exporter/pull/34) README Updates @Rosiak
### Fixed
- [#33](https://github.com/pryorda/vmware_exporter/pull/33) Drop None values in lables @akrauza

## [0.2.6] - 2018-11-24
### Changed
- Updated setup.py

### Fixed
- [#24](https://github.com/pryorda/vmware_exporter/issues/24) UTF8 Error @jnogol
