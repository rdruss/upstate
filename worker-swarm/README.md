# Upstate worker - WildFly Swarm

## Modules

The `generic-jms-ra` module is an embedded copy of
<https://github.com/jms-ra/generic-jms-ra>.  This module is not
currently published in Maven Central.  We only make use of the
`generic-jms-ra-jar` artifact.  Instead of using `generic-jms-ra-rar`,
we create our own RAR with additional dependencies for Qpid JMS.

The `qpid-jms-ra` module consists of two files.

* `qpid-jms-ra/src/main/rar/META-INF/ra.xml` - This is taken unaltered
  from the generic JMS RA RAR module.
* `qpid-jms-ra/pom.xml` - This adds the dependencies necessary to use
  Qpid JMS.

The `container` module ...