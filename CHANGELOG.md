# Change Log
All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/) and [Keep a changelog](https://github.com/olivierlacan/keep-a-changelog).

 <!--next-version-placeholder-->

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
