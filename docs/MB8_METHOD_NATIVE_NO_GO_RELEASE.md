# MB8 — method-native No-Go release

The scientific content commit `099d5ab2a0363e9fc3b78943fe311c1087004249`
was checked out in a new recursive clone. The clone was clean, reproduced parent
commit `4783b9ff9f9b6f2061a1ef8c02613f4c6cef38db` and CEO* commit
`a3f89d03e6a03c89767d3cf8ee7657a57653dda0`, passed the MB4 audit, and passed
the complete suite: 96 passed with 3 expected historical xfails.

The release preserves the decision
`NO_GO_MB4_UNRESOLVED_METHOD_NATIVE_SEMANTICS`. It publishes MB0-MB3
infrastructure and the MB4 negative result without claiming six native molecular
backends, calibration authorization, or performance.

The new annotated tag is
`v5-final-method-native-pre-calibration-no-go-v1`. Existing tags are not moved,
and branch/tag publication uses no force push. The 90-item development queue
remains unexecuted with candidate energy count zero.
